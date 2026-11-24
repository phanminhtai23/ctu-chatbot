import logoSmall from '../assets/ctu-logo-56.webp?no-inline'
import logoMedium from '../assets/ctu-logo-112.webp?no-inline'
import logoLarge from '../assets/ctu-logo-192.webp?no-inline'

type Props = {
  size?: number
}

export default function Logo({ size = 44 }: Props) {
  return (
    <img
      src={logoSmall}
      srcSet={`${logoSmall} 56w, ${logoMedium} 112w, ${logoLarge} 192w`}
      sizes={`${size}px`}
      width={size}
      height={size}
      alt="Biểu trưng CTU"
      className="shrink-0 object-contain"
      decoding="async"
    />
  )
}
