export const CONDITION_AXES = Object.freeze([
  { key: 'exit_temp', letter: 'X', label: '出炉温度', unit: '°C' },
  { key: 'process_time', letter: 'Y', label: '粗轧过程时间', unit: 's' },
  { key: 'rough_thickness', letter: 'Z', label: '粗轧厚度', unit: 'mm' }
])

// The scene uses fixed world dimensions so changing a filter never changes the
// apparent aspect ratio of a saved experiment.
export const CONDITION_SPACE = Object.freeze({
  x: Object.freeze([-5.2, 5.2]),
  y: Object.freeze([0, 6.8]),
  z: Object.freeze([-3.7, 3.7])
})

export const TEMP_DROP_STOPS = Object.freeze([
  Object.freeze([50, 105, 149]),
  Object.freeze([65, 162, 189]),
  Object.freeze([236, 202, 100]),
  Object.freeze([217, 130, 64])
])

export function finiteNumber(value) {
  if (value == null || typeof value === 'boolean' || (typeof value === 'string' && !value.trim())) return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

export function validRange(range) {
  const min = finiteNumber(range?.min)
  const max = finiteNumber(range?.max)
  return min != null && max != null && max >= min
}

export function normalizeToRange(value, range, targetRange) {
  const number = finiteNumber(value)
  const min = finiteNumber(range?.min)
  const max = finiteNumber(range?.max)
  if (number == null || min == null || max == null || max < min) return null
  const [targetMin, targetMax] = targetRange
  if (max === min) return (targetMin + targetMax) / 2
  const t = Math.max(0, Math.min(1, (number - min) / (max - min)))
  return targetMin + (targetMax - targetMin) * t
}

export function pointInConditionSpace(point, bounds) {
  return {
    x: normalizeToRange(point.exit_temp, bounds.exit_temp, CONDITION_SPACE.x),
    y: normalizeToRange(point.process_time, bounds.process_time, CONDITION_SPACE.y),
    z: normalizeToRange(point.rough_thickness, bounds.rough_thickness, CONDITION_SPACE.z)
  }
}

export function temperatureRgb(value, colorScale) {
  const number = finiteNumber(value)
  const min = finiteNumber(colorScale?.min)
  const max = finiteNumber(colorScale?.max)
  if (number == null || min == null || max == null || max < min) return [119, 131, 148]
  const t = max === min
    ? 0.5
    : Math.max(0, Math.min(1, (number - min) / (max - min)))
  const position = t * (TEMP_DROP_STOPS.length - 1)
  const index = Math.min(TEMP_DROP_STOPS.length - 2, Math.floor(position))
  const weight = position - index
  return TEMP_DROP_STOPS[index].map((channel, channelIndex) =>
    Math.round(channel + (TEMP_DROP_STOPS[index + 1][channelIndex] - channel) * weight)
  )
}

export function temperatureCss(value, colorScale) {
  return '#' + temperatureRgb(value, colorScale)
    .map(channel => channel.toString(16).padStart(2, '0'))
    .join('')
}

export function conditionTicks(range, count = 4) {
  const min = finiteNumber(range?.min)
  const max = finiteNumber(range?.max)
  if (min == null || max == null || max < min) return []
  if (max === min || count < 2) return [{ value: min, ratio: 0.5 }]
  return Array.from({ length: count }, (_, index) => {
    const ratio = index / (count - 1)
    return { value: min + (max - min) * ratio, ratio }
  })
}

export function createConditionSceneModel(data) {
  if (!data) return { state: 'empty', points: [], message: '等待已保存实验的工况快照。' }
  if (!Array.isArray(data.points)) {
    return { state: 'invalid', points: [], message: '工况快照缺少记录点，暂时无法绘制三维视图。' }
  }
  if (!data.points.length) {
    const warning = Array.isArray(data.warnings) ? data.warnings.find(item => typeof item === 'string' && item) : ''
    if (!CONDITION_AXES.every(axis => validRange(data.bounds?.[axis.key])) || !validRange(data.color_scale)) {
      return {
        state: 'invalid',
        points: [],
        message: warning || '工况快照缺少三维坐标字段或粗轧温降色标，暂时无法绘制三维视图。'
      }
    }
    return { state: 'empty', points: [], message: '本次分析没有可显示的完整工况记录。' }
  }

  const missingBounds = CONDITION_AXES.filter(axis => !validRange(data.bounds?.[axis.key]))
  if (missingBounds.length || !validRange(data.color_scale)) {
    return {
      state: 'invalid',
      points: [],
      message: '工况快照缺少三轴范围或粗轧温降色标，暂时无法绘制三维视图。'
    }
  }

  const points = data.points.filter(point =>
    point?.record_id != null &&
    CONDITION_AXES.every(axis => finiteNumber(point[axis.key]) != null) &&
    finiteNumber(point.temp_drop) != null
  )
  if (!points.length) {
    return { state: 'empty', points: [], message: '工况记录缺少绘图所需的坐标或粗轧温降。' }
  }
  return {
    state: 'ready',
    points,
    bounds: data.bounds,
    colorScale: data.color_scale,
    message: ''
  }
}
