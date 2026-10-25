type Props = {
  size?: number
}

export default function Logo({ size = 44 }: Props) {
  return (
    <img
      src="/ctu-chatbot-logo.webp"
      width={size}
      height={size}
      alt="Biểu trưng CTU"
      className="shrink-0 object-contain"
      decoding="async"
    />
  )
}
