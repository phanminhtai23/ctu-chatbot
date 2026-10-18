"""API cấp ảnh trang PDF + vị trí từng Điều để FE tô sáng đúng đoạn được tham chiếu."""

import pytest

LAYOUT = "/api/v1/documents/qd3266/layout"


@pytest.fixture()
def layout(client):
    res = client.get(LAYOUT)
    assert res.status_code == 200
    return res.json()


def test_layout_lists_every_article_with_valid_boxes(layout):
    assert layout["page_count"] == 21
    assert sorted(int(n) for n in layout["articles"]) == list(range(1, 37))
    for number, entry in layout["articles"].items():
        assert entry["title"], f"Điều {number} thiếu tiêu đề"
        assert entry["highlights"], f"Điều {number} chưa có vị trí nào"
        for h in entry["highlights"]:
            y0, x0, y1, x1 = h["box"]
            assert 1 <= h["page"] <= layout["page_count"]
            assert 0 <= y0 < y1 <= 1 and 0 <= x0 < x1 <= 1, f"Điều {number} có khung sai: {h}"
            assert str(h["page"]) in layout["pages"]


def test_articles_appear_in_document_order(layout):
    first_pages = [min(h["page"] for h in layout["articles"][str(n)]["highlights"]) for n in range(1, 37)]
    assert first_pages == sorted(first_pages), f"Điều xuất hiện sai thứ tự trang: {first_pages}"


@pytest.mark.parametrize(
    "article,page",
    [(1, 3), (6, 5), (8, 6), (14, 8), (19, 11), (24, 15), (30, 18), (32, 19)],
)
def test_known_articles_start_on_the_right_page(layout, article, page):
    pages = [h["page"] for h in layout["articles"][str(article)]["highlights"]]
    assert min(pages) == page


def test_multi_page_article_has_boxes_on_each_page(layout):
    pages = {h["page"] for h in layout["articles"]["18"]["highlights"]}  # Điều 18 dài, trải nhiều trang
    assert len(pages) >= 2


def test_page_image_is_served_as_jpeg(client):
    res = client.get("/api/v1/documents/qd3266/pages/8.jpg")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/jpeg"
    assert res.content[:2] == b"\xff\xd8"
    assert res.headers["cache-control"] == "no-cache"  # tài liệu có thể được admin thay: luôn kiểm tra lại với ETag
    assert res.headers.get("etag")


def test_every_page_has_an_image(client, layout):
    for page in range(1, layout["page_count"] + 1):
        assert client.get(f"/api/v1/documents/qd3266/pages/{page}.jpg").status_code == 200


@pytest.mark.parametrize("page", [0, 22, 999])
def test_unknown_page_is_404(client, page):
    assert client.get(f"/api/v1/documents/qd3266/pages/{page}.jpg").status_code == 404
