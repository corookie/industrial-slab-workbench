<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import {
  CONDITION_AXES,
  CONDITION_SPACE,
  conditionTicks,
  createConditionSceneModel,
  pointInConditionSpace,
  temperatureRgb
} from '../condition-space'

const props = defineProps({
  data: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  selectedId: { type: [String, Number], default: null },
  locateDisabled: { type: Boolean, default: false },
  locateNote: { type: String, default: '' }
})

const emit = defineEmits(['select', 'locate'])

const host = ref(null)
const rendererFailure = ref('')
const cameraView = ref('perspective')
const localSelectedKey = ref('')
const sampleSearch = ref('')
const tooltip = ref({ visible: false, point: null, x: 0, y: 0 })
const isMounted = ref(false)

const sceneModel = computed(() => createConditionSceneModel(props.data))
const renderedN = computed(() => sceneModel.value.state === 'ready' ? sceneModel.value.points.length : 0)
const ready = computed(() => sceneModel.value.state === 'ready')
const recordKey = record => record?.record_id == null ? '' : String(record.record_id)
const findPoint = id => sceneModel.value.points.find(point => recordKey(point) === String(id ?? '')) || null
const selectedPoint = computed(() => findPoint(props.selectedId) || findPoint(localSelectedKey.value))
const selectedKey = computed(() => recordKey(selectedPoint.value))
const count = key => props.data?.counts?.[key]

const placeholderMessage = computed(() => {
  if (rendererFailure.value) return rendererFailure.value
  if (props.error) return props.error
  if (props.loading && !props.data) return '正在读取已保存实验的工况快照…'
  return ready.value ? '' : sceneModel.value.message
})

const samplingText = computed(() => {
  if (!props.data) return ''
  return props.data.sampling === 'deterministic_record_order'
    ? '按记录顺序抽样展示；坐标范围与色标按完整有效样本计算。'
    : ''
})

const axisRanges = computed(() => CONDITION_AXES.map(axis => ({
  ...axis,
  bounds: props.data?.bounds?.[axis.key]
})))

const matchingPoints = computed(() => {
  const query = sampleSearch.value.trim().toLowerCase()
  if (!query || !ready.value) return []
  return sceneModel.value.points.filter(point => [point.record_id, point.slab_id, point.source_row]
    .some(value => String(value ?? '').toLowerCase().includes(query)))
})

const searchStatus = computed(() => {
  const query = sampleSearch.value.trim()
  if (!query) return '输入记录编号、板坯编号或来源行；按 Enter 选择，↑/↓ 切换样本。'
  return matchingPoints.value.length
    ? `匹配 ${matchingPoints.value.length.toLocaleString('zh-CN')} 条，按 Enter 选择第一条。`
    : '没有匹配的已显示样本。'
})

const selectionLiveText = computed(() => selectedPoint.value
  ? `已选择 ${pointTitle(selectedPoint.value)}。`
  : '尚未选择样本。')

function numberValue(value) {
  if (value == null || typeof value === 'boolean' || (typeof value === 'string' && !value.trim())) return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function format(value, digits = 1) {
  const number = numberValue(value)
  return number == null ? '—' : number.toLocaleString('zh-CN', { maximumFractionDigits: digits })
}

function tickFormat(value) {
  const absolute = Math.abs(Number(value))
  return format(value, absolute >= 100 ? 0 : absolute >= 10 ? 1 : 2)
}

function rangeFormat(axis, value) {
  return format(value, axis.key === 'rough_thickness' ? 2 : 1)
}

function pointTitle(point) {
  return point?.slab_id || (point?.source_row != null ? `记录 ${point.source_row}` : `记录 ${point?.record_id ?? '—'}`)
}

function dateLabel(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { hour12: false })
}

let renderer
let scene
let camera
let controls
let staticGroup
let dynamicGroup
let selectionMarker
let pointCloud
let renderedRecords = []
let recordPositions = new Map()
let resizeObserver
let intersectionObserver
let renderFrame = 0
let hoverFrame = 0
let pendingPointer
let isInViewport = true
let isDocumentVisible = typeof document === 'undefined' ? true : !document.hidden
let pointerStart
let canvasCleanup = []
let lastHostWidth = 0
let lastHostHeight = 0

const raycaster = new THREE.Raycaster()
raycaster.params.Points.threshold = 0.16
const pointer = new THREE.Vector2()
const cameraTarget = new THREE.Vector3(0, (CONDITION_SPACE.y[0] + CONDITION_SPACE.y[1]) / 2, 0)
const spritePosition = new THREE.Vector3()
const spriteProjection = new THREE.Vector3()

function requestRender() {
  if (!isMounted.value || rendererFailure.value || !renderer || !scene || !camera || renderFrame || !isInViewport || !isDocumentVisible) return
  const width = host.value?.clientWidth || 0
  const height = host.value?.clientHeight || 0
  if (!width || !height) return
  renderFrame = requestAnimationFrame(() => {
    renderFrame = 0
    if (!isMounted.value || rendererFailure.value || !renderer || !scene || !camera || !isInViewport || !isDocumentVisible) return
    updateTextSpriteScales()
    renderer.render(scene, camera)
  })
}

function resizeScene() {
  if (!renderer || !camera || !host.value) return
  const width = host.value.clientWidth
  const height = host.value.clientHeight
  if (!width || !height) {
    lastHostWidth = width
    lastHostHeight = height
    return
  }
  const previousAspect = lastHostWidth && lastHostHeight ? lastHostWidth / lastHostHeight : 0
  renderer.setSize(width, height)
  camera.aspect = width / height
  camera.updateProjectionMatrix()
  const viewportChanged = !previousAspect || Math.abs(camera.aspect - previousAspect) > 0.08
  lastHostWidth = width
  lastHostHeight = height
  if (viewportChanged) applyCameraView(cameraView.value)
  if (tooltip.value.visible && tooltip.value.point) projectTooltip(tooltip.value.point)
  requestRender()
}

function removeAndDispose(group) {
  if (!group) return
  group.parent?.remove(group)
  group.traverse(object => {
    object.geometry?.dispose()
    const materials = object.material ? (Array.isArray(object.material) ? object.material : [object.material]) : []
    materials.forEach(material => {
      Object.values(material).forEach(value => value?.isTexture && value.dispose())
      material.dispose()
    })
  })
}

function makeTextSprite(text, { accent = false, title = false, pixelHeight = accent ? 23 : 18 } = {}) {
  const canvas = document.createElement('canvas')
  const context = canvas.getContext('2d')
  const fontSize = accent ? 37 : 30
  const paddingX = accent ? 24 : 18
  const paddingY = accent ? 13 : 10
  context.font = `600 ${fontSize}px "PingFang SC", "Microsoft YaHei", sans-serif`
  const width = Math.ceil(context.measureText(text).width + paddingX * 2)
  const height = fontSize + paddingY * 2
  canvas.width = width
  canvas.height = height
  context.font = `600 ${fontSize}px "PingFang SC", "Microsoft YaHei", sans-serif`
  context.textBaseline = 'middle'
  context.fillStyle = accent ? 'rgba(38, 51, 32, .96)' : 'rgba(29, 39, 24, .84)'
  context.fillRect(0, 0, width, height)
  context.fillStyle = accent ? '#f2f7e9' : '#b8cda5'
  context.fillText(text, paddingX, height / 2 + 1)
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.minFilter = THREE.LinearFilter
  const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false, depthWrite: false })
  const sprite = new THREE.Sprite(material)
  sprite.renderOrder = 10
  sprite.userData.pixelHeight = pixelHeight
  sprite.userData.aspect = width / height
  sprite.userData.isAxisTitle = title
  sprite.scale.set((width / height) * 0.5, 0.5, 1)
  return sprite
}

function updateTextSpriteScales() {
  if (!staticGroup || !camera || !host.value) return
  const canvasWidth = host.value.clientWidth
  const canvasHeight = host.value.clientHeight
  if (!canvasHeight) return
  const occupiedRects = []
  const labels = []
  const overlaps = (a, b) => a.right + 4 > b.left && a.left - 4 < b.right && a.bottom + 4 > b.top && a.top - 4 < b.bottom
  const worldPerPixelAt = position => {
    camera.updateMatrixWorld()
    const distance = Math.max(0.1, -spriteProjection.copy(position).applyMatrix4(camera.matrixWorldInverse).z)
    return 2 * distance * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2) / canvasHeight
  }
  staticGroup.traverse(sprite => {
    const pixelHeight = sprite.isSprite && sprite.userData.pixelHeight
    if (!pixelHeight) return
    if (sprite.userData.titleAnchor) sprite.position.copy(sprite.userData.titleAnchor)
    sprite.getWorldPosition(spritePosition)
    const height = worldPerPixelAt(spritePosition) * pixelHeight
    sprite.scale.set(height * sprite.userData.aspect, height, 1)
    spriteProjection.copy(spritePosition).project(camera)
    labels.push({ sprite, depth: spriteProjection.z, halfWidth: pixelHeight * sprite.userData.aspect / 2,
      halfHeight: pixelHeight / 2, x: (spriteProjection.x + 1) * canvasWidth / 2, y: (1 - spriteProjection.y) * canvasHeight / 2 })
  })
  const rectAt = (label, x = label.x, y = label.y) => ({ left: x - label.halfWidth, right: x + label.halfWidth,
    top: y - label.halfHeight, bottom: y + label.halfHeight })
  // Crowded ticks may hide at narrow angles; full numeric ranges remain in the
  // range strip. Titles avoid both ticks and each other in CSS pixel space.
  labels.filter(label => !label.sprite.userData.isAxisTitle).forEach(label => {
    const rect = rectAt(label)
    label.sprite.visible = !occupiedRects.some(other => overlaps(rect, other))
    if (label.sprite.visible) occupiedRects.push(rect)
  })
  labels.filter(label => label.sprite.userData.isAxisTitle).forEach(label => {
    const x = Math.max(label.halfWidth + 10, Math.min(canvasWidth - label.halfWidth - 10, label.x))
    const initialY = Math.max(label.halfHeight + 10, Math.min(canvasHeight - label.halfHeight - 10, label.y))
    const step = label.halfHeight * 2 + 8
    let y = initialY
    for (let distance = 0; distance < canvasHeight; distance += step) {
      const candidates = distance ? [initialY + distance, initialY - distance] : [initialY]
      const clear = candidates.find(candidate => candidate >= label.halfHeight + 10 && candidate <= canvasHeight - label.halfHeight - 10 &&
        !occupiedRects.some(other => overlaps(rectAt(label, x, candidate), other)))
      if (clear !== undefined) { y = clear; break }
    }
    occupiedRects.push(rectAt(label, x, y))
    label.sprite.visible = true
    label.sprite.center.set(0.5, 0.5)
    spriteProjection.set(x / canvasWidth * 2 - 1, 1 - y / canvasHeight * 2, label.depth).unproject(camera)
    label.sprite.position.copy(label.sprite.parent.worldToLocal(spriteProjection))
  })
}

function makePointTexture() {
  const canvas = document.createElement('canvas')
  canvas.width = 64
  canvas.height = 64
  const context = canvas.getContext('2d')
  const gradient = context.createRadialGradient(32, 32, 1, 32, 32, 30)
  gradient.addColorStop(0, 'rgba(255,255,255,1)')
  gradient.addColorStop(0.72, 'rgba(255,255,255,1)')
  gradient.addColorStop(1, 'rgba(255,255,255,0)')
  context.fillStyle = gradient
  context.fillRect(0, 0, 64, 64)
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.minFilter = THREE.LinearFilter
  texture.magFilter = THREE.LinearFilter
  texture.generateMipmaps = false
  return texture
}

function addLineSegments(group, values, color, opacity = 1) {
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(values, 3))
  const material = new THREE.LineBasicMaterial({ color, transparent: opacity < 1, opacity })
  group.add(new THREE.LineSegments(geometry, material))
}

function buildStaticScene(model) {
  removeAndDispose(staticGroup)
  const group = new THREE.Group()
  const [xMin, xMax] = CONDITION_SPACE.x
  const [yMin, yMax] = CONDITION_SPACE.y
  const [zMin, zMax] = CONDITION_SPACE.z
  const gridValues = []
  const addSegment = (a, b) => gridValues.push(...a, ...b)
  const xTicks = conditionTicks(model.bounds.exit_temp)
  const yTicks = conditionTicks(model.bounds.process_time)
  const zTicks = conditionTicks(model.bounds.rough_thickness)

  xTicks.forEach(({ ratio }) => {
    const x = xMin + (xMax - xMin) * ratio
    addSegment([x, yMin, zMin], [x, yMin, zMax])
    addSegment([x, yMin, zMin], [x, yMax, zMin])
  })
  zTicks.forEach(({ ratio }) => {
    const z = zMin + (zMax - zMin) * ratio
    addSegment([xMin, yMin, z], [xMax, yMin, z])
    addSegment([xMin, yMin, z], [xMin, yMax, z])
  })
  yTicks.forEach(({ ratio }) => {
    const y = yMin + (yMax - yMin) * ratio
    addSegment([xMin, y, zMin], [xMax, y, zMin])
    addSegment([xMin, y, zMin], [xMin, y, zMax])
  })
  addLineSegments(group, gridValues, '#3f5036', 0.62)

  const frameGeometry = new THREE.BoxGeometry(xMax - xMin, yMax - yMin, zMax - zMin)
  const frame = new THREE.LineSegments(
    new THREE.EdgesGeometry(frameGeometry),
    new THREE.LineBasicMaterial({ color: '#637757', transparent: true, opacity: 0.75 })
  )
  frameGeometry.dispose()
  frame.position.set((xMin + xMax) / 2, (yMin + yMax) / 2, (zMin + zMax) / 2)
  group.add(frame)

  // Keep each annotated axis on a visible outer edge.  The data coordinates
  // still use the same complete-snapshot bounds; only the label placement moves.
  addLineSegments(group, [xMin, yMin, zMax, xMax + 0.46, yMin, zMax], '#cef577')
  addLineSegments(group, [xMin, yMin, zMax, xMin, yMax + 0.4, zMax], '#e6bf69')
  addLineSegments(group, [xMax, yMin, zMin, xMax, yMin, zMax + 0.45], '#89c69b')

  const xLabel = makeTextSprite('X  出炉温度 / °C', { accent: true, title: true })
  xLabel.position.set(0, yMin - 1.05, zMax + 0.4)
  xLabel.userData.titleAnchor = xLabel.position.clone()
  group.add(xLabel)
  const yLabel = makeTextSprite('Y  粗轧过程时间 / s', { accent: true, title: true })
  yLabel.position.set(xMin - 0.78, yMax + 0.78, zMax + 0.12)
  yLabel.userData.titleAnchor = yLabel.position.clone()
  group.add(yLabel)
  const zLabel = makeTextSprite('Z  粗轧厚度 / mm', { accent: true, title: true })
  zLabel.position.set(xMax + 0.9, yMin - 0.95, 0)
  zLabel.userData.titleAnchor = zLabel.position.clone()
  group.add(zLabel)

  xTicks.forEach(({ value, ratio }) => {
    const sprite = makeTextSprite(tickFormat(value))
    sprite.position.set(xMin + (xMax - xMin) * ratio, yMin - 0.43, zMax + 0.24)
    group.add(sprite)
  })
  yTicks.forEach(({ value, ratio }) => {
    const sprite = makeTextSprite(tickFormat(value))
    sprite.position.set(xMin - 0.72, yMin + (yMax - yMin) * ratio, zMax + 0.12)
    group.add(sprite)
  })
  zTicks.forEach(({ value, ratio }) => {
    const sprite = makeTextSprite(tickFormat(value))
    sprite.position.set(xMax + 0.6, yMin - 0.43, zMin + (zMax - zMin) * ratio)
    group.add(sprite)
  })

  staticGroup = group
  scene.add(group)
}

function buildPoints(model) {
  removeAndDispose(dynamicGroup)
  const group = new THREE.Group()
  const positions = new Float32Array(model.points.length * 3)
  const colors = new Float32Array(model.points.length * 3)
  const workingColor = new THREE.Color()
  renderedRecords = model.points
  recordPositions = new Map()

  model.points.forEach((record, index) => {
    const position = pointInConditionSpace(record, model.bounds)
    const color = temperatureRgb(record.temp_drop, model.colorScale)
    const offset = index * 3
    positions[offset] = position.x
    positions[offset + 1] = position.y
    positions[offset + 2] = position.z
    workingColor.setRGB(color[0] / 255, color[1] / 255, color[2] / 255, THREE.SRGBColorSpace)
    colors[offset] = workingColor.r
    colors[offset + 1] = workingColor.g
    colors[offset + 2] = workingColor.b
    recordPositions.set(recordKey(record), new THREE.Vector3(position.x, position.y, position.z))
  })

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  geometry.computeBoundingSphere()
  const material = new THREE.PointsMaterial({
    map: makePointTexture(),
    size: 5.5,
    sizeAttenuation: false,
    vertexColors: true,
    transparent: true,
    opacity: 0.9,
    alphaTest: 0.1,
    depthWrite: false,
    fog: false
  })
  pointCloud = new THREE.Points(geometry, material)
  pointCloud.renderOrder = 2
  group.add(pointCloud)
  dynamicGroup = group
  scene.add(group)
}

function ensureSelectionMarker() {
  if (selectionMarker) return
  const core = new THREE.Mesh(
    new THREE.SphereGeometry(0.16, 16, 12),
    new THREE.MeshBasicMaterial({ color: '#fff3c4', transparent: true, opacity: 0.98, depthTest: false })
  )
  const shell = new THREE.Mesh(
    new THREE.SphereGeometry(0.24, 16, 12),
    new THREE.MeshBasicMaterial({ color: '#fff4c8', transparent: true, opacity: 0.23, wireframe: true, depthTest: false })
  )
  selectionMarker = new THREE.Group()
  selectionMarker.add(core, shell)
  selectionMarker.renderOrder = 8
  selectionMarker.visible = false
  scene.add(selectionMarker)
}

function updateSelectionMarker() {
  if (!isMounted.value || !selectionMarker) return
  const position = recordPositions.get(selectedKey.value)
  selectionMarker.visible = Boolean(position)
  if (position) selectionMarker.position.copy(position)
  requestRender()
}

function syncScene() {
  if (!isMounted.value) return
  hideTooltip()
  if (!ready.value || rendererFailure.value) {
    removeAndDispose(dynamicGroup)
    removeAndDispose(staticGroup)
    dynamicGroup = undefined
    staticGroup = undefined
    pointCloud = undefined
    renderedRecords = []
    recordPositions = new Map()
    updateSelectionMarker()
    return
  }
  if (!ensureRenderer()) return
  buildStaticScene(sceneModel.value)
  buildPoints(sceneModel.value)
  ensureSelectionMarker()
  updateSelectionMarker()
  resetView()
  resizeScene()
  requestRender()
}

function ensureRenderer() {
  if (renderer) return true
  if (!host.value) return false
  try {
    scene = new THREE.Scene()
    scene.background = new THREE.Color('#181f18')
    camera = new THREE.PerspectiveCamera(38, 1, 0.1, 1000)
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.domElement.setAttribute('role', 'img')
    renderer.domElement.setAttribute('aria-label', '三维工况点云，可用工具栏搜索或键盘选择样本')
    renderer.domElement.style.touchAction = 'none'
    host.value.appendChild(renderer.domElement)

    controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = false
    controls.enablePan = false
    controls.minDistance = 6
    controls.maxDistance = 200
    controls.addEventListener('change', onControlsChange)
    bindCanvasEvents(renderer.domElement)
    resizeObserver = new ResizeObserver(resizeScene)
    resizeObserver.observe(host.value)
    if ('IntersectionObserver' in window) {
      intersectionObserver = new IntersectionObserver(entries => {
        isInViewport = entries.some(entry => entry.isIntersecting)
        if (isInViewport) {
          resizeScene()
          requestRender()
        }
      }, { threshold: 0.02 })
      intersectionObserver.observe(host.value)
    }
    document.addEventListener('visibilitychange', onDocumentVisibility)
    return true
  } catch (error) {
    rendererFailure.value = '三维视图暂不可用，请使用支持 WebGL 的浏览器。工况统计和记录详情仍可查看。'
    console.warn('Condition scene WebGL initialization failed', error)
    return false
  }
}

function onControlsChange() {
  if (tooltip.value.visible && tooltip.value.point) projectTooltip(tooltip.value.point)
  requestRender()
}

function onDocumentVisibility() {
  isDocumentVisible = !document.hidden
  if (isDocumentVisible) {
    resizeScene()
    requestRender()
  }
}

function bindCanvasEvents(canvas) {
  const listen = (name, handler) => {
    canvas.addEventListener(name, handler)
    canvasCleanup.push(() => canvas.removeEventListener(name, handler))
  }
  listen('pointermove', onPointerMove)
  listen('pointerleave', hideTooltip)
  listen('pointerdown', onPointerDown)
  listen('pointerup', onPointerUp)
  listen('webglcontextlost', onContextLost)
}

function onContextLost(event) {
  event.preventDefault()
  rendererFailure.value = '三维视图已失去 WebGL 上下文，请刷新页面后重试。'
  cancelAnimationFrame(renderFrame)
  renderFrame = 0
  hideTooltip()
}

function eventPoint(event) {
  if (!renderer || !pointCloud) return null
  const rect = renderer.domElement.getBoundingClientRect()
  if (!rect.width || !rect.height) return null
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
  raycaster.setFromCamera(pointer, camera)
  const hit = raycaster.intersectObject(pointCloud, false)[0]
  return hit?.index == null ? null : renderedRecords[hit.index] || null
}

function onPointerMove(event) {
  pendingPointer = { clientX: event.clientX, clientY: event.clientY }
  if (hoverFrame) return
  hoverFrame = requestAnimationFrame(() => {
    hoverFrame = 0
    const next = pendingPointer
    pendingPointer = undefined
    const point = next && eventPoint(next)
    if (renderer?.domElement) renderer.domElement.style.cursor = point ? 'pointer' : 'grab'
    if (point) projectTooltip(point)
    else hideTooltip()
  })
}

function onPointerDown(event) {
  if (event.button !== 0) return
  pointerStart = { x: event.clientX, y: event.clientY }
  if (renderer?.domElement) renderer.domElement.style.cursor = 'grabbing'
}

function onPointerUp(event) {
  if (event.button !== 0) return
  const moved = pointerStart && Math.hypot(event.clientX - pointerStart.x, event.clientY - pointerStart.y)
  pointerStart = undefined
  const point = moved != null && moved < 6 ? eventPoint(event) : null
  if (renderer?.domElement) renderer.domElement.style.cursor = point ? 'pointer' : 'grab'
  if (point) choosePoint(point)
}

function projectTooltip(point) {
  const position = recordPositions.get(recordKey(point))
  const width = host.value?.clientWidth || 0
  const height = host.value?.clientHeight || 0
  if (!position || !camera || !width || !height) return hideTooltip()
  const projected = position.clone().project(camera)
  if (projected.z > 1) return hideTooltip()
  tooltip.value = {
    visible: true,
    point,
    x: Math.max(12, Math.min(width - 12, (projected.x + 1) * 0.5 * width)),
    y: Math.max(12, Math.min(height - 12, (-projected.y + 1) * 0.5 * height))
  }
}

function hideTooltip() {
  if (tooltip.value.visible) tooltip.value = { visible: false, point: null, x: 0, y: 0 }
}

function fittedDistance(plan) {
  if (!camera) return 20
  const width = host.value?.clientWidth || 800
  const height = host.value?.clientHeight || 385
  const verticalTangent = Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2)
  const horizontalTangent = verticalTangent * Math.max(camera.aspect, 0.3)
  const availableX = Math.max(0.4, 1 - 2 * Math.min(78, width * 0.2) / width)
  const availableY = Math.max(0.5, 1 - 60 / height)
  const right = new THREE.Vector3().crossVectors(plan.up, plan.direction).normalize()
  const up = new THREE.Vector3().crossVectors(plan.direction, right).normalize()
  let distance = 10
  // Include the axis annotations as well as the data box; account for
  // perspective depth so the front bottom corner cannot clip the labels.
  for (const x of [-6.1, 6.2]) for (const y of [-1.1, 7.7]) for (const z of [-3.9, 4.15]) {
    const relative = new THREE.Vector3(x, y, z).sub(cameraTarget)
    const depth = relative.dot(plan.direction)
    distance = Math.max(distance,
      depth + Math.abs(relative.dot(right)) / (horizontalTangent * availableX),
      depth + Math.abs(relative.dot(up)) / (verticalTangent * availableY))
  }
  return distance * 1.03
}

function cameraPlan(view) {
  if (view === 'x') return { direction: new THREE.Vector3(1, 0, 0), up: new THREE.Vector3(0, 1, 0), horizontal: 18, vertical: 13 }
  if (view === 'y') return { direction: new THREE.Vector3(0, 1, 0), up: new THREE.Vector3(0, 0, -1), horizontal: 22, vertical: 15 }
  if (view === 'z') return { direction: new THREE.Vector3(0, 0, 1), up: new THREE.Vector3(0, 1, 0), horizontal: 22, vertical: 13 }
  return { direction: new THREE.Vector3(1, 0.72, 1).normalize(), up: new THREE.Vector3(0, 1, 0), horizontal: 20, vertical: 14 }
}

function applyCameraView(view) {
  if (!camera || !controls) return
  const plan = cameraPlan(view)
  camera.up.copy(plan.up)
  camera.position.copy(cameraTarget).addScaledVector(plan.direction, fittedDistance(plan))
  controls.target.copy(cameraTarget)
  camera.lookAt(cameraTarget)
  controls.update()
  requestRender()
}

function resetView() {
  cameraView.value = 'perspective'
  applyCameraView('perspective')
}

function setAxisView(axis) {
  cameraView.value = axis
  applyCameraView(axis)
}

function choosePoint(point) {
  if (!point) return
  localSelectedKey.value = recordKey(point)
  emit('select', point.record_id)
  updateSelectionMarker()
}

function navigateSample(delta) {
  const points = sceneModel.value.points
  if (!points.length) return
  const selectedIndex = points.findIndex(point => recordKey(point) === selectedKey.value)
  const base = selectedIndex < 0 ? (delta > 0 ? -1 : 0) : selectedIndex
  choosePoint(points[(base + delta + points.length) % points.length])
}

function chooseFirstMatch() {
  if (matchingPoints.value.length) choosePoint(matchingPoints.value[0])
}

function locateSelected() {
  if (selectedPoint.value && !props.locateDisabled) emit('locate', selectedPoint.value.record_id)
}

watch(() => props.data, () => {
  localSelectedKey.value = findPoint(localSelectedKey.value) ? localSelectedKey.value : ''
  nextTick(syncScene)
})

watch(selectedPoint, () => {
  if (tooltip.value.point && !findPoint(recordKey(tooltip.value.point))) hideTooltip()
  nextTick(updateSelectionMarker)
}, { flush: 'post' })

onMounted(() => {
  isMounted.value = true
  syncScene()
})

onBeforeUnmount(() => {
  isMounted.value = false
  cancelAnimationFrame(renderFrame)
  cancelAnimationFrame(hoverFrame)
  resizeObserver?.disconnect()
  intersectionObserver?.disconnect()
  document.removeEventListener('visibilitychange', onDocumentVisibility)
  canvasCleanup.forEach(cleanup => cleanup())
  canvasCleanup = []
  controls?.removeEventListener('change', onControlsChange)
  controls?.dispose()
  removeAndDispose(dynamicGroup)
  removeAndDispose(staticGroup)
  if (selectionMarker) {
    selectionMarker.parent?.remove(selectionMarker)
    selectionMarker.traverse(object => {
      object.geometry?.dispose()
      const materials = object.material ? (Array.isArray(object.material) ? object.material : [object.material]) : []
      materials.forEach(material => material.dispose())
    })
  }
  renderer?.dispose()
  renderer?.domElement?.remove()
})
</script>

<template>
  <section
    class="condition-scene"
    :class="{ 'has-placeholder': Boolean(placeholderMessage) }"
    :data-analysis-id="data?.analysis_id || ''"
    :data-rendered-n="renderedN"
    :data-selected-id="selectedKey"
    :data-camera-view="cameraView"
    aria-label="三维工况空间"
  >
    <header class="condition-heading">
      <div>
        
        <h3>三维工况空间</h3>
        
      </div>
      <span v-if="loading" class="scene-status">正在更新</span>
    </header>

    <div class="condition-toolbar" aria-label="三维工况视图工具">
      <div class="view-tools">
        <button type="button" class="view-button" aria-label="重置三维工况视角" @click="resetView">重置</button>
        <button type="button" class="view-button" aria-label="从 X 轴正视" :class="{ active: cameraView === 'x' }" @click="setAxisView('x')">X 视图</button>
        <button type="button" class="view-button" aria-label="从 Y 轴正视" :class="{ active: cameraView === 'y' }" @click="setAxisView('y')">Y 视图</button>
        <button type="button" class="view-button" aria-label="从 Z 轴正视" :class="{ active: cameraView === 'z' }" @click="setAxisView('z')">Z 视图</button>
      </div>
      <div class="sample-tools">
        <label class="sample-search">
          <span class="sr-only">搜索三维样本</span>
          <input
            v-model="sampleSearch"
            type="search"
            aria-label="搜索三维样本"
            aria-describedby="condition-search-status"
            placeholder="搜索记录 / 板坯 / 行号"
            title="按 Enter 选择，↑/↓ 切换匹配样本"
            :disabled="!ready"
            @keydown.enter.prevent="chooseFirstMatch"
            @keydown.down.prevent="navigateSample(1)"
            @keydown.up.prevent="navigateSample(-1)"
          >
        </label>
        <button type="button" class="step-button" aria-label="上一个三维样本" :disabled="!ready" @click="navigateSample(-1)">‹</button>
        <button type="button" class="step-button" aria-label="下一个三维样本" :disabled="!ready" @click="navigateSample(1)">›</button>
      </div>
    </div>
    <p v-show="sampleSearch.trim()" id="condition-search-status" class="search-status" aria-live="polite">{{ searchStatus }}</p>

    <div v-if="data" class="axis-range-bar" aria-label="三维坐标范围">
      <div v-for="axis in axisRanges" :key="axis.key" class="axis-range">
        <b>{{ axis.letter }}</b>
        <span>{{ axis.label }} / {{ axis.unit }}</span>
        <strong>{{ rangeFormat(axis, axis.bounds?.min) }}—{{ rangeFormat(axis, axis.bounds?.max) }}</strong>
      </div>
    </div>

    <div class="condition-stage">
      <div ref="host" class="condition-canvas-host" :aria-busy="loading"></div>
      <div v-if="placeholderMessage" class="scene-placeholder" role="status">{{ placeholderMessage }}</div>
      <div
        v-if="tooltip.visible && tooltip.point"
        class="point-tooltip"
        :style="{ left: `${tooltip.x}px`, top: `${tooltip.y}px` }"
      >
        <strong>{{ pointTitle(tooltip.point) }}</strong>
        <span>{{ tooltip.point.steel_grade || '钢种未提供' }} · 温降 {{ format(tooltip.point.temp_drop, 1) }} °C</span>
        
      </div>
    </div>
    <p v-if="ready && !placeholderMessage" class="scene-instruction">拖动旋转 · 滚轮缩放 · 点击点选择</p>

    <div class="scene-summary" aria-label="工况快照计数">
      <div v-if="count('eligible')!==renderedN"><span>完整坐标样本</span><strong>{{ format(count('eligible'), 0) }}</strong></div>
      <div v-if="count('missing_coordinates')>0"><span>缺坐标</span><strong>{{ format(count('missing_coordinates'), 0) }}</strong></div>
      <div><span>显示点数</span><strong>{{ format(renderedN, 0) }}</strong></div>
    </div>

    <div class="color-legend" aria-label="粗轧温降固定色标">
      <div class="legend-heading"><span>颜色：粗轧温降 / °C</span></div>
      <div class="legend-gradient"></div>
      <div class="legend-values"><span>{{ format(data?.color_scale?.min, 1) }}</span><span>{{ format(data?.color_scale?.max, 1) }}</span></div>
    </div>

    <p v-if="samplingText" class="sampling-note">{{ samplingText }}</p>
    <details class="scene-method"><summary>图示说明</summary><p>每个点对应一条记录，坐标表示工况参数，颜色表示整体温降，不是空间温度场。色标按本次分析的全部有效样本固定；重叠点优先选择离视点最近的记录。</p></details>

    <section v-if="selectedPoint" class="condition-selection" aria-label="已选工况样本详情">
      <div class="selection-heading">
        <div>
          <span class="scene-kicker">已选样本</span>
          <h4>{{ pointTitle(selectedPoint) }}</h4>
          <p>{{ selectedPoint.steel_grade || '钢种未提供' }} · 来源行 {{ selectedPoint.source_row ?? '—' }}</p>
        </div>
        <button
          type="button"
          class="locate-button"
          aria-label="在记录表中查看"
          :disabled="locateDisabled"
          :aria-describedby="locateDisabled ? 'condition-locate-note' : undefined"
          @click="locateSelected"
        >在记录表中查看</button>
      </div>
      <div class="selection-metrics">
        <div><span>出炉温度</span><strong data-testid="condition-selected-exit-temp">{{ format(selectedPoint.exit_temp, 1) }} <small>°C</small></strong></div>
        <div><span>粗轧过程时间</span><strong data-testid="condition-selected-process-time">{{ format(selectedPoint.process_time, 1) }} <small>s</small></strong></div>
        <div><span>粗轧厚度</span><strong data-testid="condition-selected-rough-thickness">{{ format(selectedPoint.rough_thickness, 2) }} <small>mm</small></strong></div>
        <div><span>粗轧温降</span><strong data-testid="condition-selected-temp-drop">{{ format(selectedPoint.temp_drop, 1) }} <small>°C</small></strong></div>
      </div>
      <p v-if="selectedPoint.produced_at" class="selection-time">生产时间：{{ dateLabel(selectedPoint.produced_at) }}</p><details class="selection-time"><summary>记录标识</summary><p>记录标识：{{ selectedPoint.record_id }}</p></details>
      <p v-if="locateDisabled" id="condition-locate-note" class="locate-note">{{ locateNote || '当前工作台筛选与保存实验范围不一致，请按保存分析范围查看记录。' }}</p>
    </section>
    <p class="sr-only" aria-live="polite">{{ selectionLiveText }}</p>
  </section>
</template>

<style scoped>
.condition-scene{margin:0 0 18px;border:1px solid #425338;border-radius:8px;overflow:hidden;background:#222b20;color:#dce6d2;box-shadow:0 8px 18px rgba(22,51,72,.1)}
.condition-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding:16px 18px 13px;background:linear-gradient(110deg,#263320,#222b20 72%);border-bottom:1px solid #425338}.scene-kicker{display:block;color:#aabe91;font-size:10px;letter-spacing:.12em;font-weight:700;margin-bottom:4px}.condition-heading h3,.condition-heading h4{margin:0;color:#f2f7e9;font-size:16px;font-weight:650}.condition-heading p,.selection-heading p{margin:4px 0 0;color:#b2c29e;font-size:11px}.scene-status{flex:none;padding:4px 7px;border:1px solid #3f657c;border-radius:3px;color:#cfdfbc;font-size:10px;white-space:nowrap}.condition-toolbar{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 12px;background:#293524;border-bottom:1px solid #425338}.view-tools,.sample-tools{display:flex;align-items:center;gap:5px}.view-button,.step-button,.locate-button{border:1px solid #566b45;border-radius:4px;background:#34462a;color:#d4e2c6;font-size:11px;line-height:1.2;padding:6px 8px;white-space:nowrap}.view-button:hover,.step-button:hover,.view-button.active{background:#526d38;color:#f3fbff}.step-button{font-size:18px;line-height:.8;padding:5px 8px;min-width:30px}.view-button:focus-visible,.step-button:focus-visible,.locate-button:focus-visible,.sample-search input:focus-visible{outline:2px solid #82bddc;outline-offset:2px}.sample-search input{width:172px;border:1px solid #566b45;border-radius:4px;background:#1c2817;color:#e6f4fb;padding:6px 8px;font-size:11px;line-height:1.2}.sample-search input::placeholder{color:#9eae8e}.step-button:disabled,.locate-button:disabled{opacity:.52;cursor:not-allowed}.search-status{min-height:17px;margin:0;padding:4px 13px;color:#aabe91;background:#293524;font-size:10px;line-height:1.45}.axis-range-bar{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;border-bottom:1px solid #425338;background:#425338}.axis-range{display:grid;grid-template-columns:auto minmax(0,1fr);gap:1px 7px;align-items:center;padding:7px 11px;background:#293524;min-width:0}.axis-range b{grid-row:1 / span 2;color:#cef577;font-size:13px}.axis-range span{overflow:hidden;color:#b4c99b;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.axis-range strong{color:#f2f7e9;font-size:11px;font-weight:600;font-variant-numeric:tabular-nums;white-space:nowrap}.condition-stage{position:relative;background:#181f18}.condition-canvas-host{width:100%;height:385px;position:relative}.condition-canvas-host canvas{width:100%;height:100%;display:block;touch-action:none}.scene-placeholder{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:30px;text-align:center;color:#b6ccda;font-size:13px;line-height:1.65;background:radial-gradient(circle at center,#12334a,#181f18 70%)}.scene-instruction{position:absolute;right:12px;bottom:10px;border:1px solid rgba(100,149,176,.36);border-radius:3px;background:rgba(7,24,39,.77);padding:4px 6px;color:#9ab6c7;font-size:10px;pointer-events:none}.point-tooltip{position:absolute;z-index:4;max-width:250px;transform:translate(12px,calc(-100% - 10px));padding:8px 10px;border:1px solid #52809a;border-radius:5px;background:rgba(5,24,39,.96);box-shadow:0 7px 18px rgba(0,0,0,.28);pointer-events:none;font-size:11px;line-height:1.5}.point-tooltip strong,.point-tooltip span{display:block}.point-tooltip strong{color:#f3f7e2;font-size:12px}.point-tooltip span{color:#b4cbd7}.point-tooltip span:last-child{margin-top:3px;color:#7fa0b3;font-size:10px}.scene-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border-top:1px solid #425338;border-bottom:1px solid #425338;background:#293524}.scene-summary div{padding:10px 12px;border-right:1px solid #425338;min-width:0}.scene-summary div:last-child{border-right:0}.scene-summary span{display:block;color:#aabe91;font-size:10px}.scene-summary strong{display:block;margin-top:2px;color:#f2f7e9;font-size:18px;font-weight:600;font-variant-numeric:tabular-nums}.color-legend{padding:12px 14px 10px;background:#293524}.legend-heading{display:flex;justify-content:space-between;gap:12px;color:#d4e2c6;font-size:11px}.legend-heading small{color:#7f9db1;font-size:10px}.legend-gradient{height:8px;margin:7px 0 3px;border:1px solid rgba(255,255,255,.14);border-radius:2px;background:linear-gradient(90deg,#326995,#41a2bd,#ecca64,#d98240)}.legend-values{display:flex;justify-content:space-between;color:#aabe91;font-size:10px;font-variant-numeric:tabular-nums}.sampling-note,.scene-method{margin:0;padding:8px 14px;color:#aabe91;background:#293524;font-size:10px;line-height:1.65}.scene-method{padding-top:2px;padding-bottom:13px;color:#aabe91;border-top:1px solid rgba(80,122,147,.25)}.condition-selection{border-top:1px solid #385c72;background:#edf4e0;color:#35442a}.selection-heading{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:13px 14px 10px;border-bottom:1px solid #d1debf}.selection-heading .scene-kicker{color:#70835d}.selection-heading h4{color:#394f2c;font-size:15px}.selection-heading p{color:#70835d}.locate-button{background:#405b2c;border-color:#405b2c;color:#fff;font-size:11px}.locate-button:not(:disabled):hover{background:#344d24}.selection-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;background:#dce7ce}.selection-metrics>div{padding:11px 12px;background:#fafcf5;min-width:0}.selection-metrics span{display:block;color:#70835d;font-size:10px}.selection-metrics strong{display:block;margin-top:3px;color:#425b2f;font-size:16px;font-weight:650;font-variant-numeric:tabular-nums;white-space:nowrap}.selection-metrics small{font-size:10px;font-weight:500;color:#70835d}.selection-time,.locate-note{margin:0;padding:9px 14px;color:#70835d;font-size:10px;line-height:1.55}.locate-note{padding-top:0;color:#9a6b3f}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.scene-instruction{position:static;margin:0;border:0;border-radius:0;text-align:right;padding:6px 12px;background:#181f18}
.scene-summary{display:flex;flex-wrap:wrap}.scene-summary>div{display:flex;align-items:center;gap:10px;flex:1}.scene-summary strong{margin:0;font-size:14px}.scene-method{padding-top:8px}.scene-method summary{cursor:pointer;font-size:12px}.scene-method p{margin-top:8px;line-height:1.7}.selection-time summary{cursor:pointer}
@media(max-width:760px){.condition-canvas-host{height:350px}.condition-toolbar{align-items:stretch;flex-direction:column}.view-tools{justify-content:space-between}.view-button{flex:1;padding-left:5px;padding-right:5px}.sample-tools{width:100%}.sample-search{flex:1}.sample-search input{width:100%}.axis-range{padding:7px 8px;gap:1px 5px}.axis-range span{font-size:9px}.axis-range strong{font-size:10px}.condition-selection{margin:0}.selection-metrics{grid-template-columns:1fr 1fr}.selection-metrics>div{padding:10px 12px}.scene-summary strong{font-size:16px}}
@media(max-width:420px){.condition-heading{padding:14px 13px 11px}.condition-heading h3{font-size:15px}.condition-heading p{font-size:10px}.condition-canvas-host{height:315px}.view-tools{gap:3px}.view-button{font-size:10px;padding:6px 4px}.axis-range{padding:6px 5px;gap:1px 4px}.axis-range b{font-size:12px}.axis-range span{font-size:8px}.axis-range strong{font-size:9px;letter-spacing:-.02em}.scene-summary div{padding:9px 8px}.scene-summary span{font-size:9px}.scene-summary strong{font-size:14px}.legend-heading small{display:none}.selection-heading{align-items:flex-start;padding:12px}.locate-button{padding:6px 7px;font-size:10px}.selection-metrics>div{padding:9px 10px}.selection-metrics strong{font-size:15px}.point-tooltip{max-width:210px}.scene-instruction{font-size:9px;right:8px;bottom:8px}}

.condition-scene{border-radius:18px;box-shadow:none;border-color:#4c603f;background:#222b20}
.condition-heading{background:#222b20;padding:20px}.condition-heading h3{font-size:18px}.condition-toolbar{padding:12px 16px}
.view-button,.step-button,.locate-button{border-radius:8px;font-size:12px;padding:9px 10px;min-height:34px}.view-button.active{background:#cef577;color:#27391a;border-color:#cef577}
.sample-search input{font-size:12px;padding:9px 10px;height:36px;border-radius:8px;color:#edf6e4}.scene-status{border-radius:6px;font-size:11px;border-color:#5d744a;color:#c9dfb3}
.scene-placeholder{background:#181f18;color:#b9cdaa}.scene-instruction{background:#181f18;color:#b0c698;font-size:11px;padding:10px 16px}
.axis-range{padding:10px 12px}.axis-range span{font-size:11px}.axis-range strong{font-size:12px}.scene-summary div{padding:12px 16px}.scene-summary span{font-size:12px}.scene-summary strong{font-size:17px}
.point-tooltip{border-color:#789c56;background:rgba(25,36,19,.96);border-radius:10px}.point-tooltip span,.point-tooltip span:last-child{color:#b8cea4}
.color-legend{padding:16px}.legend-heading,.legend-values{font-size:12px;color:#c1d5ae}.sampling-note,.scene-method{font-size:12px;padding:12px 16px}.scene-method summary{font-size:13px}
.selection-heading{padding:18px}.selection-heading h4{font-size:18px}.selection-heading p{font-size:12px}.selection-metrics>div{padding:16px}.selection-metrics span{font-size:12px}.selection-metrics strong{font-size:19px}.selection-time,.locate-note{font-size:12px;padding-left:18px;padding-right:18px}
@media(max-width:760px){.condition-heading{padding:16px}.condition-heading h3{font-size:16px}.condition-toolbar{padding:12px}.view-tools{flex-wrap:wrap}.view-button{font-size:11px;padding:8px 5px}.sample-search input{width:100%}.axis-range{padding:9px 5px;gap:2px 4px}.axis-range span{font-size:9px}.axis-range strong{font-size:10px}.selection-heading{flex-wrap:wrap}.selection-metrics>div{padding:14px 12px}.selection-metrics strong{font-size:17px}.scene-summary span{font-size:11px}}
</style>
