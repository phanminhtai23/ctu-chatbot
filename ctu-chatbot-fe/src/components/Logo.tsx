type Props = {
  size?: number
}

export default function Logo({ size = 52 }: Props) {
  return (
    <img
      src="/ctu-chatbot-avatar.webp"
      width={size}
      height={size}
      alt="Mascot CTU Chatbot"
      className="shrink-0 object-contain"
      decoding="async"
    />
  )
}
