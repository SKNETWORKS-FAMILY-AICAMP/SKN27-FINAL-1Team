export const shouldRevealAppBanner = (pathname, scrollY, viewportHeight) => (
  pathname !== '/' || scrollY >= viewportHeight * 0.4
)
