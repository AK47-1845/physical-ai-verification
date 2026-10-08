'use client';

import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { sampleTrace, type Failure } from '@/lib/demo';

export default function RobotScene({ failure = 'nominal', hero = false, paused = false, sampleIndex }: { failure?: Failure; hero?: boolean; paused?: boolean; sampleIndex?: number }) {
  const host = useRef<HTMLDivElement>(null);
  const state = useRef({ failure, paused, sampleIndex });
  const [failed, setFailed] = useState(false);
  useEffect(() => { state.current = { failure, paused, sampleIndex }; }, [failure, paused, sampleIndex]);
  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let renderer: THREE.WebGLRenderer;
    try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true, powerPreference: 'low-power' }); }
    catch {
      const failureFrame = requestAnimationFrame(() => setFailed(true));
      return () => cancelAnimationFrame(failureFrame);
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    renderer.setClearColor('#0c0f10', 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.65;
    renderer.domElement.setAttribute('role', 'img');
    renderer.domElement.setAttribute('aria-label', 'Articulated robotic arm following a cyan verification trajectory. Synthetic visualization.');
    element.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight('#e6f5ef', '#142322', 3));
    const key = new THREE.DirectionalLight('#ffffff', 5);
    key.position.set(-3, 5, 4);
    scene.add(key);
    const rim = new THREE.DirectionalLight('#8fe7e0', 3);
    rim.position.set(3, 2, -4);
    scene.add(rim);
    const camera = new THREE.PerspectiveCamera(34, 1, 0.01, 30);
    const silver = new THREE.MeshStandardMaterial({ color: '#bdc9c6', metalness: .72, roughness: .29 });
    const dark = new THREE.MeshStandardMaterial({ color: '#182326', metalness: .55, roughness: .3 });
    const cyan = new THREE.MeshStandardMaterial({ color: '#70d5cf', emissive: '#2e726c', emissiveIntensity: .5, metalness: .3, roughness: .3 });
    const white = new THREE.MeshStandardMaterial({ color: '#e6eae5', metalness: .4, roughness: .25 });
    const base = new THREE.Mesh(new THREE.CylinderGeometry(.18, .23, .10, 48), dark);
    base.position.y = .05;
    scene.add(base);
    const plate = new THREE.Mesh(new THREE.BoxGeometry(.75, .03, .65), new THREE.MeshStandardMaterial({ color: '#283638', metalness: .5, roughness: .65 }));
    plate.position.set(0, -.008, 0);
    scene.add(plate);
    for (const horizontal of [-1, 1]) for (const depth of [-1, 1]) {
      const bolt = new THREE.Mesh(new THREE.CylinderGeometry(.016, .016, .018, 12), silver);
      bolt.position.set(horizontal * .31, .016, depth * .26);
      scene.add(bolt);
    }
    const column = new THREE.Mesh(new THREE.CylinderGeometry(.095, .13, .28, 40), white);
    column.position.y = .23;
    scene.add(column);
    const shoulderPosition = new THREE.Vector3(0, .40, 0);
    function joint(radius: number) {
      const group = new THREE.Group();
      const body = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, radius * 1.7, 40), dark);
      body.rotation.z = Math.PI / 2;
      group.add(body);
      for (const side of [-1, 1]) {
        const cap = new THREE.Mesh(new THREE.CylinderGeometry(radius * .72, radius * .72, .018, 32), silver);
        cap.rotation.z = Math.PI / 2;
        cap.position.x = side * radius * .87;
        group.add(cap);
        const center = new THREE.Mesh(new THREE.CylinderGeometry(radius * .3, radius * .3, .019, 24), cyan);
        center.rotation.z = Math.PI / 2;
        center.position.x = side * radius * .98;
        group.add(center);
      }
      scene.add(group);
      return group;
    }
    const shoulder = joint(.12);
    shoulder.position.copy(shoulderPosition);
    const elbow = joint(.10);
    const wrist = joint(.075);
    const upper = new THREE.Mesh(new THREE.CylinderGeometry(.075, .095, 1, 40), white);
    const forearm = new THREE.Mesh(new THREE.CylinderGeometry(.058, .078, 1, 40), silver);
    scene.add(upper, forearm);
    const gripper = new THREE.Group();
    gripper.add(new THREE.Mesh(new THREE.BoxGeometry(.15, .07, .12), dark));
    for (const side of [-1, 1]) {
      const finger = new THREE.Mesh(new THREE.BoxGeometry(.025, .13, .055), silver);
      finger.position.set(side * .063, -.09, 0);
      gripper.add(finger);
    }
    scene.add(gripper);
    const grid = new THREE.GridHelper(hero ? 9 : 5, hero ? 72 : 40, '#3c5956', '#213332');
    grid.position.y = -.04;
    scene.add(grid);
    const pathPoints = Array.from({ length: 120 }, (_, index) => new THREE.Vector3(...sampleTrace(index).intended));
    const tube = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pathPoints), 180, .0035, 6, false);
    scene.add(new THREE.Mesh(tube, new THREE.MeshBasicMaterial({ color: '#83ece4', transparent: true, opacity: .8 })));
    scene.add(new THREE.Points(new THREE.BufferGeometry().setFromPoints(pathPoints.filter((_, index) => index % 4 === 0)), new THREE.PointsMaterial({ color: '#b5fcf1', size: .016 })));
    const envelope = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(1.08, 1.1, .92)), new THREE.LineBasicMaterial({ color: '#3d6863', transparent: true, opacity: .5 }));
    envelope.position.set(.36, .55, 0);
    scene.add(envelope);
    const target = new THREE.Mesh(new THREE.BoxGeometry(.12, .08, .12), cyan);
    target.position.set(.54, .05, -.22);
    scene.add(target);
    const marker = new THREE.Mesh(new THREE.SphereGeometry(.014, 16, 12), new THREE.MeshBasicMaterial({ color: '#ddfff1' }));
    scene.add(marker);
    const badPath = new THREE.Line(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: '#ffa18b' }));
    scene.add(badPath);
    let lastFailure: Failure | undefined;
    const connect = (mesh: THREE.Mesh, start: THREE.Vector3, end: THREE.Vector3) => {
      const direction = end.clone().sub(start);
      mesh.position.copy(start).add(end).multiplyScalar(.5);
      mesh.scale.y = direction.length();
      mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize());
    };
    const resize = () => {
      const width = element.clientWidth;
      const height = Math.max(1, element.clientHeight);
      renderer.setSize(width, height);
      camera.aspect = width / height;
      const heroWide = hero && width >= 768;
      camera.position.set(heroWide ? 2.95 : 2.65, heroWide ? 2.1 : 1.85, heroWide ? 3.9 : 3.5);
      camera.lookAt(heroWide ? -.85 : .3, heroWide ? .36 : .53, 0);
      camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    let visible = true;
    const intersection = new IntersectionObserver(entries => { visible = entries[0].isIntersecting; }, { rootMargin: '100px' });
    intersection.observe(element);
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    let frame = 0;
    let tick = 0;
    let lastTime = 0;
    const render = (time: number) => {
      frame = requestAnimationFrame(render);
      if (!visible || document.hidden || time - lastTime < 16) return;
      const elapsed = Math.min(50, time - lastTime);
      lastTime = time;
      if (!reduced.matches && !state.current.paused) tick += elapsed * .02;
      const index = state.current.sampleIndex ?? (reduced.matches ? 76 : Math.floor(tick % 120));
      const point = sampleTrace(index, state.current.failure);
      const position = new THREE.Vector3(...point.observed);
      const elbowPosition = new THREE.Vector3(-.16 + position.x * .20, 1.06, position.z * .28);
      const wristPosition = position.clone().add(new THREE.Vector3(0, .16, 0));
      elbow.position.copy(elbowPosition);
      wrist.position.copy(wristPosition);
      connect(upper, shoulderPosition, elbowPosition);
      connect(forearm, elbowPosition, wristPosition);
      gripper.position.copy(position).add(new THREE.Vector3(0, .07, 0));
      marker.position.copy(position);
      if (lastFailure !== state.current.failure) {
        lastFailure = state.current.failure;
        badPath.geometry.dispose();
        badPath.geometry = new THREE.BufferGeometry().setFromPoints(Array.from({ length: 120 }, (_, sample) => new THREE.Vector3(...sampleTrace(sample, lastFailure).observed)));
        badPath.visible = lastFailure === 'drift';
        cyan.color.set(lastFailure === 'nominal' ? '#70d5cf' : '#e7a38f');
      }
      renderer.render(scene, camera);
      element.dataset.rendered = 'true';
      element.dataset.frame = String(index);
    };
    resize();
    frame = requestAnimationFrame(render);
    return () => {
      cancelAnimationFrame(frame); observer.disconnect(); intersection.disconnect();
      scene.traverse(object => {
        const mesh = object as THREE.Mesh;
        mesh.geometry?.dispose();
        if (mesh.material) for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) material.dispose();
      });
      renderer.dispose(); renderer.forceContextLoss(); renderer.domElement.remove();
    };
  }, [hero]);
  return <div ref={host} className="robot-scene" data-testid={hero ? 'hero-scene' : 'demo-scene'}>{failed ? <img className="scene-poster" src="/robot-poster.webp" width="1280" height="720" alt="Static verification trace of a robotic arm. WebGL unavailable." /> : null}</div>;
}
