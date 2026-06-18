"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, type ThreeEvent, useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import type { VectorAtlasData } from "@/lib/types";
import { translateGenre } from "@/lib/genres";

const PALETTE = [
  "#f5b50a", "#ff6b6b", "#4ecdc4", "#a78bfa", "#f472b6", "#34d399",
  "#60a5fa", "#fb923c", "#facc15", "#c084fc", "#2dd4bf", "#fda4af",
  "#84cc16", "#38bdf8", "#e879f9", "#fde047", "#5eead4", "#f87171",
  "#818cf8", "#a3e635",
];

function colorForGenre(index: number): THREE.Color {
  return new THREE.Color(PALETTE[index % PALETTE.length]);
}

function PointCloud({
  data,
  onHover,
}: {
  data: VectorAtlasData;
  onHover: (info: { index: number; x: number; y: number } | null) => void;
}) {
  const { raycaster } = useThree();

  useEffect(() => {
    raycaster.params.Points = { threshold: 0.45 };
  }, [raycaster]);

  const { positions, colors } = useMemo(() => {
    const count = data.x.length;
    const positions = new Float32Array(count * 3);
    const colors = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      positions[i * 3] = data.x[i];
      positions[i * 3 + 1] = data.y[i];
      positions[i * 3 + 2] = data.z[i];
      const color = colorForGenre(data.g[i]);
      colors[i * 3] = color.r;
      colors[i * 3 + 1] = color.g;
      colors[i * 3 + 2] = color.b;
    }
    return { positions, colors };
  }, [data]);

  function handlePointerMove(event: ThreeEvent<PointerEvent>) {
    event.stopPropagation();
    if (event.index === undefined) return;
    onHover({ index: event.index, x: event.clientX, y: event.clientY });
  }

  return (
    <points onPointerMove={handlePointerMove} onPointerOut={() => onHover(null)}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[colors, 3]} />
      </bufferGeometry>
      <pointsMaterial
        size={0.16}
        vertexColors
        sizeAttenuation
        transparent
        opacity={0.85}
        depthWrite={false}
      />
    </points>
  );
}

export default function VectorAtlas({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<VectorAtlasData | null>(null);
  const [error, setError] = useState(false);
  const [hover, setHover] = useState<{ index: number; x: number; y: number } | null>(null);

  useEffect(() => {
    fetch("/movie-vectors-3d.json")
      .then((response) => {
        if (!response.ok) throw new Error("not ok");
        return response.json();
      })
      .then(setData)
      .catch(() => setError(true));
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-night-950">
      <div className="relative border-b border-night-700 px-4 py-5 sm:px-6">
        <button
          type="button"
          onClick={onClose}
          className="absolute right-4 top-5 rounded-lg border border-night-600 px-3 py-1.5 text-sm text-screen-300 transition-colors hover:border-marquee-500/50 hover:text-marquee-300 sm:right-6"
        >
          Voltar à busca
        </button>
        <div className="text-center">
          <h2 className="font-display text-3xl font-bold uppercase tracking-wide text-screen-100 sm:text-4xl">
            Universo dos Filmes
          </h2>
          <p className="mt-2 text-sm text-marquee-400 sm:text-base">
            Cada filme é um vetor no espaço com aproximação por similaridade
          </p>
        </div>
      </div>

      <div className="relative flex-1">
        {error && (
          <div className="absolute inset-0 flex items-center justify-center text-screen-300">
            Não foi possível carregar o gráfico de vetores.
          </div>
        )}

        {data && !error && (
          <Canvas camera={{ position: [0, 0, 75], fov: 55 }}>
            <ambientLight intensity={0.8} />
            <PointCloud data={data} onHover={setHover} />
            <OrbitControls
              autoRotate
              autoRotateSpeed={0.4}
              enableDamping
              dampingFactor={0.08}
              minDistance={10}
              maxDistance={150}
            />
          </Canvas>
        )}

        {data && !error && (
          <div className="pointer-events-none absolute left-4 top-1/2 flex max-h-[70vh] -translate-y-1/2 flex-col gap-1.5 overflow-y-auto rounded-lg border border-night-700 bg-night-900/80 p-3 text-[11px] text-screen-300 backdrop-blur-sm sm:left-6">
            {data.genres.map((genre, index) => (
              <span key={genre} className="flex items-center gap-1.5">
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ backgroundColor: PALETTE[index % PALETTE.length] }}
                />
                {translateGenre(genre)}
              </span>
            ))}
          </div>
        )}

        {data && !error && (
          <p className="pointer-events-none absolute bottom-3 right-4 max-w-[60vw] text-right text-[10px] leading-snug text-screen-500/70 sm:right-6">
            Para visualização, os vetores foram redimensionados para três
            dimensões, simplificando sua representação.
          </p>
        )}

        {hover && data && (
          <div
            className="pointer-events-none fixed z-10 max-w-xs rounded-md border border-night-600 bg-night-950/95 px-3 py-1.5 text-sm text-screen-100 shadow-lg"
            style={{ left: hover.x + 14, top: hover.y + 14 }}
          >
            {data.t[hover.index]}
          </div>
        )}
      </div>
    </div>
  );
}
