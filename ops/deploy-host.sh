#!/usr/bin/env bash
set -Eeuo pipefail
log_deploy_error() {
    local status=$1 line=$2 command=$3
    printf "Deploy failed at %s:%d (exit %d): %s\n" "${BASH_SOURCE[1]:-$0}" "$line" "$status" "$command" >&2
    exit "$status"
}
trap 'log_deploy_error "$?" "$LINENO" "$BASH_COMMAND"' ERR

project=/home/opc/projects/ctu-chatbot
stage=${1:?Missing deployment staging directory}
web_root=/usr/share/nginx/html/ctu-chatbot
site=/etc/nginx/conf.d/ctu-chatbot.conf
locations=/etc/nginx/ctu-chatbot.locations.conf
host=ctu-chatbot.io.vn
env_file="$project/ctu-chatbot-be/.env"
image_repo="ghcr.io/${IMAGE_OWNER:?}/${IMAGE_NAME:?}-backend"
[[ ${IMAGE_TAG:?} =~ ^[0-9a-f]{40}$ ]]
test -f "$env_file"

# Keep Compose project names and volumes identical across the switch.
compose=(docker compose --project-directory "$project" --project-name ctu-chatbot --env-file "$env_file")
next_compose=("${compose[@]}" -f "$stage/docker-compose.prod.yml")
cp "$project/docker-compose.prod.yml" "$stage/previous-compose.yml"
old_compose=("${compose[@]}" -f "$stage/previous-compose.yml")
old_backend=$("${old_compose[@]}" ps -q backend)
old_image=
if [[ -n "$old_backend" ]]; then
    old_image=$(docker inspect --format '{{.Config.Image}}' "$old_backend")
    [[ "$old_image" == "$image_repo":* ]]
fi

# The first deployment replaces the old proxy location and keeps the Certbot server blocks.
cp "$site" "$stage/previous-site.conf"
if [[ -f "$locations" ]]; then
    cp "$locations" "$stage/previous-locations.conf"
fi
python3 - "$stage/previous-site.conf" "$stage/next-site.conf" "$locations" <<'PY'
from pathlib import Path
import re
import sys

original, target, locations = sys.argv[1:]
text = Path(original).read_text()
include = f"    include {locations};"
if include not in text.splitlines():
    legacy = r"^    location / \{\n(?=\s*proxy_pass http://127\.0\.0\.1:8080;)[\s\S]*?^    \}"
    text, replacements = re.subn(legacy, include, text, flags=re.MULTILINE)
    if replacements != 1:
        raise SystemExit("Expected one CTU frontend proxy block in the host Nginx site")
Path(target).write_text(text)
PY

sudo -n install -d -m 0755 -o "$(id -u)" -g "$(id -g)" "$web_root" "$web_root/releases"
old_current=$(readlink "$web_root/current" || true)
old_previous=$(readlink "$web_root/previous" || true)
release=$(mktemp -d "$web_root/releases/$IMAGE_TAG.XXXXXXXX")
link_stage=
backend_changed=false
links_changed=false
nginx_changed=false
published=false

set_release_link() {
    local link=$1 target=$2
    if [[ -n "$target" ]]; then
        ln -sfn -- "$target" "$link_stage/$link"
        mv -Tf -- "$link_stage/$link" "$web_root/$link"
    else
        rm -f -- "$web_root/$link"
    fi
}

legacy_frontends() {
    docker ps "$@" -q --filter label=com.docker.compose.project=ctu-chatbot \
        --filter label=com.docker.compose.service=frontend
}

finish() {
    local result=$?
    trap - ERR
    set +e
    if (( result != 0 )) && ! "$published"; then
        if "$links_changed"; then
            set_release_link current "$old_current"
            set_release_link previous "$old_previous"
        fi
        if "$nginx_changed"; then
            sudo -n install -m 0644 "$stage/previous-site.conf" "$site"
            if [[ -f "$stage/previous-locations.conf" ]]; then
                sudo -n install -m 0644 "$stage/previous-locations.conf" "$locations"
            else
                sudo -n rm -f -- "$locations"
            fi
            sudo -n nginx -t && sudo -n systemctl reload nginx
        fi
        if "$backend_changed" && [[ -n "$old_image" ]]; then
            IMAGE_TAG="${old_image##*:}" "${old_compose[@]}" up -d --wait --wait-timeout 180 backend
            for container in $(legacy_frontends); do
                docker exec "$container" nginx -s reload
            done
        fi
        rm -rf -- "$release"
    fi
    if [[ -n "$link_stage" ]]; then
        rm -rf -- "$link_stage"
    fi
    exit "$result"
}
trap finish EXIT

link_stage=$(mktemp -d "$web_root/.links.XXXXXXXX")
tar --no-same-owner --no-same-permissions -xzf "$stage/frontend.tar.gz" -C "$release"
test -s "$release/index.html"
test -d "$release/assets"
chmod -R a+rX "$release"
chmod 0755 "$release"
if command -v restorecon >/dev/null; then
    sudo -n restorecon -R "$web_root"
fi

for attempt in 1 2 3; do
    if "${next_compose[@]}" pull backend; then
        break
    fi
    if (( attempt == 3 )); then
        echo "Backend image pull failed after $attempt attempts" >&2
        exit 1
    fi
    sleep "$((attempt * 10))"
done

backend_changed=true
"${next_compose[@]}" up -d --wait --wait-timeout 300 backend
curl -fsS --max-time 10 http://127.0.0.1:8000/api/v1/health >/dev/null

links_changed=true
set_release_link previous "$old_current"
set_release_link current "releases/${release##*/}"

if ! cmp -s "$site" "$stage/next-site.conf" || ! cmp -s "$locations" "$stage/ctu-chatbot.locations.conf"; then
    nginx_changed=true
    sudo -n install -m 0644 "$stage/ctu-chatbot.locations.conf" "$locations"
    sudo -n install -m 0644 "$stage/next-site.conf" "$site"
    sudo -n nginx -t
    sudo -n systemctl reload nginx
fi

https=(curl -fsS --max-time 5 --noproxy "$host" --resolve "$host:443:127.0.0.1")

check_frontend() {
    local path=$1
    if ! "${https[@]}" -o "$stage/probe.html" "https://$host$path"; then
        echo "HTTPS $path is not ready" >&2
        return 1
    fi
    if ! cmp -s "$stage/probe.html" "$release/index.html"; then
        echo "HTTPS $path is not serving the new frontend yet" >&2
        return 1
    fi
}

# systemctl reload returns before Nginx finishes starting workers with the new config.
for attempt in {1..12}; do
    if check_frontend / && check_frontend /chat &&
       "${https[@]}" -o /dev/null "https://$host/api/v1/health"; then
        break
    fi
    if (( attempt == 12 )); then
        echo "HTTPS checks failed after $attempt attempts; rolling back the release" >&2
        exit 1
    fi
    sleep 2
done

mv -f -- "$stage/docker-compose.prod.yml" "$project/docker-compose.prod.yml"
published=true
echo "Backend and static frontend are healthy"

# Retire the old CTU frontend only after the HTTPS checks pass.
for container in $(legacy_frontends -a); do
    docker stop "$container" && docker rm "$container" || true
done
frontend_repo="ghcr.io/$IMAGE_OWNER/$IMAGE_NAME-frontend"
for tag in $(docker image ls --format '{{.Tag}}' "$frontend_repo"); do
    if [[ "$tag" == latest || "$tag" =~ ^[0-9a-f]{40}$ ]]; then
        docker image rm "$frontend_repo:$tag" || true
    fi
done
for tag in $(docker image ls --format '{{.Tag}}' "$image_repo"); do
    if [[ "$tag" =~ ^[0-9a-f]{40}$ && "$tag" != "$IMAGE_TAG" && "$tag" != "${old_image##*:}" ]]; then
        docker image rm "$image_repo:$tag" || true
    fi
done
for dir in "$web_root/releases/"*; do
    if [[ "${dir##*/}" =~ ^[0-9a-f]{40}\.[a-zA-Z0-9]{8}$ &&
          "$dir" != "$release" && "releases/${dir##*/}" != "$old_current" ]]; then
        rm -rf -- "$dir" || true
    fi
done
