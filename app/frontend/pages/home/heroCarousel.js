export const wrapSlideIndex = (index, total) => (index + total) % total

export const getDragDirection = (distance, threshold = 48) => (
  Math.abs(distance) < threshold ? 0 : distance < 0 ? 1 : -1
)
