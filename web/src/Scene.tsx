import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import type { Trace } from './types'

interface SceneState { render: () => void; update: (index: number) => void; reset: (top: boolean) => void }

export default function Scene({ trace, index, top, resetKey }: { trace: Trace; index: number; top: boolean; resetKey: number }) {
  const container = useRef<HTMLDivElement>(null)
  const state = useRef<SceneState | null>(null)
  const indexRef = useRef(index)
  indexRef.current = index

  useEffect(() => {
    const element = container.current
    if (!element) return
    const scene = new THREE.Scene()
    scene.background = new THREE.Color('#17211f')
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true })
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.4
    renderer.domElement.setAttribute('aria-label', 'Interactive task-space trajectory replay')
    renderer.domElement.setAttribute('role', 'img')
    element.appendChild(renderer.domElement)
    const camera = new THREE.PerspectiveCamera(38, 1, 0.01, 30)
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = false
    controls.minDistance = 0.5
    controls.maxDistance = 5
    controls.maxPolarAngle = Math.PI * 0.49
    controls.enablePan = true
    const render = () => renderer.render(scene, camera)
    controls.addEventListener('change', render)
    scene.add(new THREE.HemisphereLight('#f7fffa', '#334940', 3))
    const key = new THREE.DirectionalLight('#ffffff', 4)
    key.position.set(1, 3, 2)
    scene.add(key)
    const rim = new THREE.DirectionalLight('#bafad6', 2)
    rim.position.set(-2, 1, -2)
    scene.add(rim)
    scene.add(new THREE.GridHelper(3, 30, '#52645b', '#2b3a33'))
    const axes = new THREE.AxesHelper(0.23)
    axes.position.set(-0.25, 0.005, 0.45)
    scene.add(axes)
    const point = (coordinates: number[]) => new THREE.Vector3(coordinates[0], coordinates.length > 2 ? coordinates[2] : 0.018, coordinates[1])
    const referencePoints = trace.reference.map(point)
    const observedPoints = trace.observed.map(point)
    const addPath = (points: THREE.Vector3[], color: string, dashed: boolean) => {
      const geometry = new THREE.BufferGeometry().setFromPoints(points)
      const material = dashed ? new THREE.LineDashedMaterial({ color, dashSize: 0.025, gapSize: 0.018 }) : new THREE.LineBasicMaterial({ color })
      const line = new THREE.Line(geometry, material)
      line.computeLineDistances()
      scene.add(line)
      scene.add(new THREE.Points(geometry.clone(), new THREE.PointsMaterial({ color, size: 0.008, sizeAttenuation: true })))
    }
    addPath(referencePoints, '#78daa8', false)
    addPath(observedPoints, '#ff947d', false)
    const silver = new THREE.MeshStandardMaterial({ color: '#e5e9e6', metalness: 0.58, roughness: 0.27 })
    const graphite = new THREE.MeshStandardMaterial({ color: '#29332f', metalness: 0.5, roughness: 0.38 })
    const accent = new THREE.MeshStandardMaterial({ color: '#82dbad', metalness: 0.25, roughness: 0.32 })
    const arm = new THREE.Group()
    const base = new THREE.Mesh(new THREE.CylinderGeometry(0.085, 0.11, 0.07, 48), graphite)
    base.position.y = 0.035
    arm.add(base)
    const riser = new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.068, 0.17, 40), silver)
    riser.position.y = 0.14
    arm.add(riser)
    const makeJoint = (radius: number) => new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, radius * 1.7, 40), graphite)
    const shoulder = makeJoint(0.065)
    shoulder.rotation.z = Math.PI / 2
    shoulder.position.set(0, 0.24, 0)
    arm.add(shoulder)
    const elbow = makeJoint(0.06)
    elbow.rotation.z = Math.PI / 2
    arm.add(elbow)
    const wrist = new THREE.Mesh(new THREE.SphereGeometry(0.045, 28, 24), graphite)
    arm.add(wrist)
    const upper = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.05, 1, 36), silver)
    const lower = new THREE.Mesh(new THREE.CylinderGeometry(0.032, 0.043, 1, 36), silver)
    arm.add(upper, lower)
    const band = new THREE.Mesh(new THREE.CylinderGeometry(0.051, 0.051, 0.025, 36), accent)
    arm.add(band)
    const gripper = new THREE.Group()
    gripper.add(new THREE.Mesh(new THREE.BoxGeometry(0.075, 0.045, 0.06), graphite))
    for (const side of [-1, 1]) {
      const finger = new THREE.Mesh(new THREE.BoxGeometry(0.012, 0.065, 0.028), silver)
      finger.position.set(side * 0.032, -0.04, 0)
      gripper.add(finger)
    }
    arm.add(gripper)
    if (trace.observed[0].length === 3) scene.add(arm)
    const observedMarker = new THREE.Mesh(new THREE.SphereGeometry(0.017, 24, 20), new THREE.MeshBasicMaterial({ color: '#ffad96' }))
    const referenceMarker = new THREE.Mesh(new THREE.SphereGeometry(0.012, 24, 20), new THREE.MeshBasicMaterial({ color: '#91ffd0' }))
    scene.add(observedMarker, referenceMarker)
    const errorGeometry = new THREE.BufferGeometry().setFromPoints([observedPoints[0], referencePoints[0]])
    scene.add(new THREE.Line(errorGeometry, new THREE.LineBasicMaterial({ color: '#fce9b0' })))
    const connect = (mesh: THREE.Mesh, start: THREE.Vector3, end: THREE.Vector3) => {
      const direction = end.clone().sub(start)
      mesh.position.copy(start).add(end).multiplyScalar(0.5)
      mesh.scale.y = direction.length()
      mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize())
    }
    const update = (sample: number) => {
      const position = observedPoints[Math.min(sample, observedPoints.length - 1)]
      const intended = referencePoints[Math.min(sample, referencePoints.length - 1)]
      observedMarker.position.copy(position)
      referenceMarker.position.copy(intended)
      const elbowPosition = new THREE.Vector3(-0.09 + position.x * 0.35, 0.7, position.z * 0.4)
      const wristPosition = position.clone().add(new THREE.Vector3(0, 0.10, 0))
      elbow.position.copy(elbowPosition)
      wrist.position.copy(wristPosition)
      connect(upper, shoulder.position, elbowPosition)
      connect(lower, elbowPosition, wristPosition)
      band.position.copy(elbowPosition).lerp(wristPosition, 0.12)
      band.quaternion.copy(lower.quaternion)
      gripper.position.copy(position).add(new THREE.Vector3(0, 0.045, 0))
      errorGeometry.setFromPoints([position, intended])
      render()
    }
    const bounds = new THREE.Box3().setFromPoints([...referencePoints, ...observedPoints, new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, 0.8, 0)])
    const center = bounds.getCenter(new THREE.Vector3())
    const reset = (overhead: boolean) => {
      controls.target.copy(center)
      camera.up.set(0, 1, 0)
      camera.position.copy(center).add(overhead ? new THREE.Vector3(0.001, 2.3, 0.02) : new THREE.Vector3(1.65, 1.03, 1.85))
      controls.update()
      render()
    }
    const resize = () => {
      const width = element.clientWidth
      const height = element.clientHeight
      renderer.setSize(width, height)
      camera.aspect = width / Math.max(1, height)
      camera.updateProjectionMatrix()
      render()
    }
    const observer = new ResizeObserver(resize)
    observer.observe(element)
    state.current = { render, update, reset }
    reset(false)
    resize()
    update(indexRef.current)
    return () => {
      state.current = null
      observer.disconnect()
      controls.dispose()
      scene.traverse((object) => {
        const mesh = object as THREE.Mesh
        mesh.geometry?.dispose()
        if (mesh.material) for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) material.dispose()
      })
      renderer.dispose()
      renderer.forceContextLoss()
      renderer.domElement.remove()
    }
  }, [trace])

  useEffect(() => { state.current?.update(index) }, [index])
  useEffect(() => { state.current?.reset(top) }, [top, resetKey])

  return <div ref={container} className="scene-canvas" data-testid="trajectory-canvas" />
}