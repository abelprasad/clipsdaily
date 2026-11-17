import React from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  Sequence,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { Audio } from "@remotion/media";

// ---------------------------------------------------------------------------
// Types — the whole ad is driven by src/script.json (see README: variants).
// ---------------------------------------------------------------------------
export type BeatKind = "hook" | "receipt" | "total" | "alternative" | "cta";

export type Beat = {
  id: string;
  kind: BeatKind;
  text: string;
  voice: string;
  minSeconds: number;
  subtext?: string;
};

export type ScriptData = {
  title: string;
  fps: number;
  width: number;
  height: number;
  voice: {
    engine: string;
    model: string;
    modelPath: string;
    lengthScale?: number;
  };
  beats: Beat[];
  timings: Record<string, number> | null;
};

export type ReceiptReelProps = {
  script: ScriptData;
};

type BeatPlan = Beat & {
  startFrame: number;
  frames: number;
  seconds: number;
};

// Beat length = generated voiceover length (+0.4s tail, baked into `timings`
// by `npm run voiceover`), falling back to minSeconds when no timings exist.
export function getBeatPlan(script: ScriptData, fps: number): BeatPlan[] {
  let cursor = 0;
  return script.beats.map((beat) => {
    const seconds = script.timings?.[beat.id] ?? beat.minSeconds;
    const frames = Math.round(seconds * fps);
    const plan: BeatPlan = { ...beat, startFrame: cursor, frames, seconds };
    cursor += frames;
    return plan;
  });
}

export function getTotalFrames(script: ScriptData, fps: number): number {
  return getBeatPlan(script, fps).reduce((sum, b) => sum + b.frames, 0);
}

// ---------------------------------------------------------------------------
// Design tokens — system fonts only, no paid assets.
// Unslop v4: weights capped at 600 (Arial resolves to Liberation Sans on the
// render box, which has no 600 face — Chromium renders 600 as Bold; the
// token is capped, the raster reads bold). One accent (amber) used rarely:
// the money that matters + the clip-coins. Coral is gone.
// ---------------------------------------------------------------------------
const BG = "#0B0E11";
const PANEL = "#141A20";
const PANEL_LINE = "rgba(237,237,237,0.08)";
const WHITE = "#FFFFFF";
const MUTED = "#9AA5B1";
const AMBER = "#F5B942";
const AMBER_DEEP = "#C98A1B";
const FONT = "Arial, Helvetica, sans-serif";

// Background palette — dark and muted on purpose, so the game layer never
// fights the copy. The scrim below does the rest.
const SKY_FAR = "#131B24";
const SKY_MID = "#18222E";
const GROUND = "#0C1117";
const GROUND_EDGE = "#1D2833";
const LANE = "#22303C";
const RUNNER = "#4C5A54";
const RUNNER_LIGHT = "#5B6B62";
const MOON = "#EDE6D0";
const WINDOW = "#E8E2D4";

// Money amounts ($49/mo, $19–29/mo, $199) always render amber.
const MONEY_RE = /(\$[0-9][0-9.,–-]*(?:\/mo)?)/g;

function renderMoney(text: string): React.ReactNode {
  return text.split(MONEY_RE).map((part, i) =>
    MONEY_RE.test(part) || /^\$/.test(part) ? (
      <span
        key={i}
        style={{ color: AMBER, fontVariantNumeric: "tabular-nums" }}
      >
        {part}
      </span>
    ) : (
      <React.Fragment key={i}>{part}</React.Fragment>
    ),
  );
}

// ---------------------------------------------------------------------------
// Deterministic pseudo-random (same value every render — no flicker).
// ---------------------------------------------------------------------------
const mod = (n: number, m: number) => ((n % m) + m) % m;
const rand = (seed: number) => {
  const x = Math.sin(seed * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
};
const smooth = (t: number) => t * t * (3 - 2 * t);

// ---------------------------------------------------------------------------
// Animated background — endless-runner scene, drawn entirely in code.
// No ripped footage, no copyrighted assets. Depths (slow → fast): stars →
// far skyline → mid skyline (lit windows) → ground + lane dashes → foreground
// posts → scrim → runner + coins + speed lines (above the scrim so the
// motion still reads, but small and dim enough to stay out of the copy's
// way). All copy sits on opaque panels, the caption pill, or the scrim —
// legibility is structural, not luck. World: a streamer's city at 2 a.m.
// after the stream ends. Signature: the clip-coin trail.
// ---------------------------------------------------------------------------
type Building = {
  x: number;
  w: number;
  h: number;
  antenna: boolean;
  step: boolean;
  windows: { dx: number; dy: number; s: number }[];
};

const buildSkyline = (
  count: number,
  seedBase: number,
  minW: number,
  maxW: number,
  minH: number,
  maxH: number,
  withWindows: boolean,
): { buildings: Building[]; width: number } => {
  const buildings: Building[] = [];
  let x = 0;
  for (let i = 0; i < count; i++) {
    const w = minW + rand(seedBase + i * 3) * (maxW - minW);
    const h = minH + rand(seedBase + i * 3 + 1) * (maxH - minH);
    const windows: { dx: number; dy: number; s: number }[] = [];
    if (withWindows) {
      for (let k = 0; k < 3; k++) {
        windows.push({
          dx: 12 + rand(seedBase + i * 17 + k * 5) * Math.max(10, w - 26),
          dy: 18 + rand(seedBase + i * 17 + k * 5 + 1) * Math.max(10, h - 50),
          s: 6 + rand(seedBase + i * 17 + k * 5 + 2) * 3,
        });
      }
    }
    buildings.push({
      x,
      w,
      h,
      antenna: rand(seedBase + i * 13) > 0.7,
      step: rand(seedBase + i * 19) > 0.6,
      windows,
    });
    x += w + 8 + rand(seedBase + i * 3 + 2) * 30;
  }
  return { buildings, width: x };
};

const GROUND_TOP = 1500;
const FAR = buildSkyline(16, 100, 60, 130, 120, 320, false);
const MID = buildSkyline(12, 500, 90, 180, 180, 420, true);

const STARS = Array.from({ length: 36 }, (_, i) => ({
  x: rand(900 + i * 7) * 1080,
  y: rand(900 + i * 7 + 1) * 1350,
  r: 1.5 + rand(900 + i * 7 + 2) * 2.5,
  o: 0.08 + rand(900 + i * 7 + 3) * 0.16,
  speed: 0.3 + rand(900 + i * 7 + 4) * 0.9,
}));

// Speed lines live in the runner band only, and fade in/out over travel.
const SPEED_LINES = Array.from({ length: 10 }, (_, i) => ({
  x0: rand(700 + i * 11) * 1300,
  y: 1240 + rand(700 + i * 11 + 1) * 460,
  len: 80 + rand(700 + i * 11 + 2) * 140,
  w: 2 + rand(700 + i * 11 + 5) * 2,
  speed: 12 + rand(700 + i * 11 + 3) * 7,
  o: 0.05 + rand(700 + i * 11 + 4) * 0.04,
}));

// Foreground posts — the fastest depth, dark silhouettes at the bottom edge.
const FOREGROUND = Array.from({ length: 5 }, (_, i) => ({
  x0: i * 320 + rand(600 + i) * 80,
  h: 160 + rand(600 + i + 1) * 100,
  speed: 14,
}));

const COINS_TOP = Array.from({ length: 5 }, (_, i) => ({
  x0: i * 260 + rand(300 + i) * 80,
  y: 252,
  speed: 6,
  size: 28 + (i % 3) * 4,
  phase: i * 1.3,
}));

const COINS_GROUND = Array.from({ length: 6 }, (_, i) => ({
  x0: i * 240 + rand(400 + i) * 60,
  y: 1510,
  speed: 9,
  size: 28 + (i % 3) * 4,
  phase: i * 1.7,
}));

const SkylineLayer: React.FC<{
  data: { buildings: Building[]; width: number };
  color: string;
  offset: number;
}> = ({ data, color, offset }) => (
  <>
    {[0, 1].map((copy) => (
      <div
        key={copy}
        style={{
          position: "absolute",
          left: 0,
          bottom: 1920 - GROUND_TOP,
          width: data.width,
          height: 460,
          transform: `translateX(${offset + copy * data.width}px)`,
        }}
      >
        {data.buildings.map((b, i) => (
          <div
            key={i}
            style={{
              position: "absolute",
              left: b.x,
              bottom: 0,
              width: b.w,
              height: b.h,
              backgroundColor: color,
            }}
          >
            {b.antenna ? (
              <>
                <div
                  style={{
                    position: "absolute",
                    left: b.w / 2 - 1,
                    top: -26,
                    width: 3,
                    height: 26,
                    backgroundColor: color,
                  }}
                />
                <div
                  style={{
                    position: "absolute",
                    left: b.w / 2 - 3,
                    top: -30,
                    width: 6,
                    height: 6,
                    borderRadius: "50%",
                    backgroundColor: color,
                  }}
                />
              </>
            ) : null}
            {b.step ? (
              <div
                style={{
                  position: "absolute",
                  left: b.w * 0.22,
                  top: -26,
                  width: b.w * 0.56,
                  height: 26,
                  backgroundColor: color,
                }}
              />
            ) : null}
            {b.windows.map((wn, j) => (
              <div
                key={j}
                style={{
                  position: "absolute",
                  left: wn.dx,
                  top: wn.dy,
                  width: wn.s,
                  height: wn.s + 2,
                  borderRadius: 2,
                  backgroundColor: WINDOW,
                  opacity: 0.2,
                }}
              />
            ))}
          </div>
        ))}
      </div>
    ))}
  </>
);

// ---------------------------------------------------------------------------
// Run cycle — pose-to-pose keyframes, 4 poses per stride (18 frames).
// Angles in degrees; positive = swung forward of vertical. Two-segment
// limbs: shin trails the thigh by most of the knee bend, forearm angle is
// absolute (folded forward across the body). Squash & stretch: the body
// compresses at contact (lift 0) and extends in the air (lift 10).
// ---------------------------------------------------------------------------
type RunPose = {
  hipF: number;
  kneeF: number;
  hipB: number;
  kneeB: number;
  shF: number;
  faF: number;
  shB: number;
  faB: number;
  lean: number;
  lift: number;
};

const RUN_POSES: RunPose[] = [
  // contact, right foot strikes
  { hipF: 38, kneeF: 8, hipB: -32, kneeB: 55, shF: -30, faF: 10, shB: 28, faB: 55, lean: 10, lift: 0 },
  // passing, right foot under the body
  { hipF: 5, kneeF: 35, hipB: -10, kneeB: 95, shF: -10, faF: 25, shB: 8, faB: 45, lean: 8, lift: 10 },
  // contact, left foot strikes
  { hipF: -32, kneeF: 55, hipB: 38, kneeB: 8, shF: 28, faF: 55, shB: -30, faB: 10, lean: 10, lift: 0 },
  // passing, left foot under the body
  { hipF: -10, kneeF: 95, hipB: 5, kneeB: 35, shF: 8, faF: 45, shB: -10, faB: 25, lean: 8, lift: 10 },
];

const CYCLE_FRAMES = 18;

function poseAt(frame: number): RunPose {
  const phase = mod(frame, CYCLE_FRAMES) / CYCLE_FRAMES;
  const scaled = phase * 4;
  const i = Math.floor(scaled) % 4;
  const j = (i + 1) % 4;
  const t = smooth(scaled - Math.floor(scaled));
  const a = RUN_POSES[i];
  const b = RUN_POSES[j];
  const out = {} as RunPose;
  (Object.keys(a) as (keyof RunPose)[]).forEach((k) => {
    out[k] = a[k] + (b[k] - a[k]) * t;
  });
  return out;
}

// Endpoint of a limb segment: origin, angle in degrees from straight down.
const limb = (x: number, y: number, deg: number, len: number) => {
  const r = (deg * Math.PI) / 180;
  return { x: x + Math.sin(r) * len, y: y + Math.cos(r) * len };
};

// The ClipForge courier: forward lean, cap, and a clip satchel with a play
// mark that swings against the stride (secondary motion). Hand-made wobble:
// a slow ±1.2° sway on top of the lean, so no two strides are identical.
const RunnerFigure: React.FC<{ frame: number }> = ({ frame }) => {
  const p = poseAt(frame);
  const phase = mod(frame, CYCLE_FRAMES) / CYCLE_FRAMES;
  const wobble = 1.2 * Math.sin(frame * 0.11);
  const sy = 0.95 + 0.08 * (p.lift / 10);
  const sx = 1.05 - 0.05 * (p.lift / 10);
  const satchelSwing = -7 * Math.sin(phase * Math.PI * 2);

  const hip = { x: -6, y: 104 };
  const shoulder = { x: -2, y: 48 };
  const kneeF = limb(hip.x, hip.y, p.hipF, 52);
  const footF = limb(kneeF.x, kneeF.y, p.hipF - p.kneeF * 0.9, 52);
  const kneeB = limb(hip.x, hip.y, p.hipB, 52);
  const footB = limb(kneeB.x, kneeB.y, p.hipB - p.kneeB * 0.9, 52);
  const elbowF = limb(shoulder.x, shoulder.y, p.shF, 34);
  const handF = limb(elbowF.x, elbowF.y, p.faF, 32);
  const elbowB = limb(shoulder.x, shoulder.y, p.shB, 34);
  const handB = limb(elbowB.x, elbowB.y, p.faB, 32);

  const seg = (
    x1: number,
    y1: number,
    x2: number,
    y2: number,
    w: number,
  ) => (
    <line
      x1={x1}
      y1={y1}
      x2={x2}
      y2={y2}
      stroke={RUNNER}
      strokeWidth={w}
      strokeLinecap="round"
    />
  );

  return (
    <svg
      width={200}
      height={260}
      viewBox="0 0 200 260"
      style={{ overflow: "visible" }}
    >
      <g
        transform={`translate(100, 10) rotate(${p.lean + wobble}) translate(0, ${-p.lift}) scale(${sx}, ${sy})`}
      >
        {/* satchel — behind the torso, swings against the stride */}
        <g transform={`rotate(${satchelSwing} -18 104)`}>
          <line
            x1={-2}
            y1={52}
            x2={-24}
            y2={96}
            stroke={RUNNER_LIGHT}
            strokeWidth={4}
            strokeLinecap="round"
          />
          <rect
            x={-38}
            y={88}
            width={26}
            height={32}
            rx={6}
            fill={RUNNER_LIGHT}
          />
          <path d="M -29 98 L -29 110 L -19 104 Z" fill={WHITE} opacity={0.9} />
        </g>
        {/* legs — two segments each, knee bends */}
        {seg(hip.x, hip.y, kneeB.x, kneeB.y, 15)}
        {seg(kneeB.x, kneeB.y, footB.x, footB.y, 13)}
        {seg(hip.x, hip.y, kneeF.x, kneeF.y, 15)}
        {seg(kneeF.x, kneeF.y, footF.x, footF.y, 13)}
        {/* torso */}
        {seg(0, 40, hip.x, hip.y, 22)}
        {/* arms — two segments each, elbows bent */}
        {seg(shoulder.x, shoulder.y, elbowB.x, elbowB.y, 13)}
        {seg(elbowB.x, elbowB.y, handB.x, handB.y, 11)}
        {seg(shoulder.x, shoulder.y, elbowF.x, elbowF.y, 13)}
        {seg(elbowF.x, elbowF.y, handF.x, handF.y, 11)}
        {/* head + cap */}
        <circle cx={4} cy={16} r={15} fill={RUNNER} />
        <path d="M -11 14 A 15 15 0 0 1 19 14 Z" fill={RUNNER} />
        <rect x={12} y={10} width={18} height={6} rx={3} fill={RUNNER} />
      </g>
    </svg>
  );
};

// A clip-coin: flat amber disc, flat darker ring, white play triangle.
// Spins (scaleX) AND bobs — secondary motion, not just a scroll.
const Coin: React.FC<{
  frame: number;
  x: number;
  y: number;
  size: number;
  speed: number;
  phase: number;
  index: number;
}> = ({ frame, x, y, size, speed, phase, index }) => {
  const left = mod(x - frame * speed, 1240) - 80;
  const spin = Math.abs(Math.cos(frame * 0.12 + phase));
  const bob = Math.sin(frame * 0.15 + phase) * 6;
  return (
    <div
      key={index}
      style={{
        position: "absolute",
        left,
        top: y + bob,
        width: size,
        height: size,
        borderRadius: "50%",
        backgroundColor: AMBER,
        opacity: 0.85,
        transform: `scaleX(${0.25 + 0.75 * spin})`,
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 4,
          borderRadius: "50%",
          border: `3px solid ${AMBER_DEEP}`,
        }}
      />
      <svg
        width={size * 0.36}
        height={size * 0.36}
        viewBox="0 0 12 12"
        style={{
          position: "absolute",
          left: "50%",
          top: "50%",
          transform: "translate(-42%, -50%)",
        }}
      >
        <path d="M 2 1 L 11 6 L 2 11 Z" fill={WHITE} />
      </svg>
    </div>
  );
};

const RunnerBackground: React.FC = () => {
  const frame = useCurrentFrame();
  const farX = -mod(frame * 1.2, FAR.width);
  const midX = -mod(frame * 3.5, MID.width);
  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      {/* sky — flat ink, no gradient wash */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundColor: BG,
        }}
      />
      {/* moon — one flat disc, the sky's subject */}
      <div
        style={{
          position: "absolute",
          left: 860,
          top: 180,
          width: 84,
          height: 84,
          borderRadius: "50%",
          backgroundColor: MOON,
          opacity: 0.85,
        }}
      />
      {/* stars, slow drift */}
      {STARS.map((s, i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            left: mod(s.x - frame * s.speed, 1080),
            top: s.y,
            width: s.r,
            height: s.r,
            borderRadius: "50%",
            backgroundColor: WHITE,
            opacity: s.o,
          }}
        />
      ))}
      {/* skylines, two depths */}
      <SkylineLayer data={FAR} color={SKY_FAR} offset={farX} />
      <SkylineLayer data={MID} color={SKY_MID} offset={midX} />
      {/* dusk band — one flat strip at the horizon, barely there */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: 1400,
          height: 96,
          backgroundColor: AMBER,
          opacity: 0.05,
        }}
      />
      {/* ground + lane dashes, fast — dash lengths vary */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: GROUND_TOP,
          height: 420,
          backgroundColor: GROUND,
          borderTop: `3px solid ${GROUND_EDGE}`,
        }}
      />
      {Array.from({ length: 9 }, (_, i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            left: mod(i * 160 - frame * 9, 1440) - 160,
            top: 1640,
            width: 72 + rand(i * 7) * 40,
            height: 8,
            borderRadius: 4,
            backgroundColor: LANE,
          }}
        />
      ))}
      {/* foreground posts — fastest depth */}
      {FOREGROUND.map((p, i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            left: mod(p.x0 - frame * p.speed, 1440) - 80,
            top: 1920 - p.h,
            width: 14,
            height: p.h,
            backgroundColor: "#05070A",
            opacity: 0.9,
          }}
        />
      ))}
      {/* scrim — copy never sits on raw background */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "linear-gradient(180deg, rgba(11,14,17,0.70) 0%, rgba(11,14,17,0.45) 30%, rgba(11,14,17,0.45) 68%, rgba(11,14,17,0.78) 100%)",
        }}
      />
      {/* runner — above the scrim, in the empty strip below the copy */}
      <div
        style={{
          position: "absolute",
          left: 120,
          top: 1360,
          opacity: 0.95,
          transform: "scale(1.2)",
          transformOrigin: "bottom left",
        }}
      >
        <RunnerFigure frame={frame} />
      </div>
      {/* clip-coins — two lanes, spin and bob as they scroll */}
      {[...COINS_TOP, ...COINS_GROUND].map((c, i) => (
        <Coin
          key={i}
          frame={frame}
          x={c.x0}
          y={c.y}
          size={c.size}
          speed={c.speed}
          phase={c.phase}
          index={i}
        />
      ))}
      {/* speed lines — streak and fade as they travel, runner band only */}
      {SPEED_LINES.map((l, i) => {
        const p = mod(l.x0 - frame * l.speed, 1400) / 1400;
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: p * 1400 - 160,
              top: l.y,
              width: l.len,
              height: l.w,
              borderRadius: 2,
              backgroundColor: WHITE,
              opacity: Math.min(0.12, l.o * Math.sin(Math.PI * p) * 2),
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// Kinetic text — one entrance pattern per scene, no linear moves left except
// constant-velocity world scroll (the runner runs at constant speed).
// - "fade": rise on a damped spring (slight overshoot), opacity eased out.
// - "slide": receipt rows wind up and overshoot, then settle.
// - "slam": the total / CTA wordmark scale down hard, squash on landing.
// NOTE: useCurrentFrame() is relative to the NEAREST <Sequence>, so `enterAt`
// is the offset inside this line's own Sequence (0 for lines whose Sequence
// starts exactly at their beat). Do NOT pass a global frame here — that
// double-subtracts and the line never appears.
// ---------------------------------------------------------------------------
const EASE_OUT = Easing.out(Easing.cubic);

const Line: React.FC<{
  enterAt?: number;
  kind?: "fade" | "slide" | "slam";
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({ enterAt = 0, kind = "fade", children, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const local = Math.max(0, frame - enterAt);
  const opacity = interpolate(local, [0, kind === "slam" ? 5 : 8], [0, 1], {
    easing: EASE_OUT,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  let transform = "";
  if (kind === "fade") {
    const s = spring({
      frame: local,
      fps,
      config: { damping: 13, stiffness: 220, mass: 0.8 },
    });
    transform = `translateY(${(1 - s) * 28}px)`;
  } else if (kind === "slide") {
    // Damping 11 overshoots: the row slides past its slot, then settles.
    const s = spring({
      frame: local,
      fps,
      config: { damping: 11, stiffness: 190, mass: 0.8 },
    });
    transform = `translateX(${(1 - s) * 220}px)`;
  } else {
    const s = spring({
      frame: local,
      fps,
      config: { damping: 9, stiffness: 240, mass: 0.9 },
    });
    const base = 2.2 - 1.2 * s;
    const settle = interpolate(s, [0.85, 1], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    const bump = Math.sin(settle * Math.PI);
    transform = `scale(${base * (1 + 0.05 * bump)}, ${base * (1 - 0.05 * bump)})`;
  }
  return (
    <div style={{ opacity, transform, ...style }}>{children}</div>
  );
};

// Hook words pop in one at a time on varied beats, along a slight arc; the
// $49 counts up 0 → 49 on an eased curve and squashes once as it lands.
const HookWords: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const words = text.split(" ");
  return (
    <>
      {words.map((word, i) => {
        const delay = i * 5 + (i % 3) * 2;
        const wordFrame = Math.max(0, frame - delay);
        const pop = spring({
          frame: wordFrame,
          fps,
          config: { damping: 10, stiffness: 280, mass: 0.7 },
        });
        const scale = 0.45 + 0.55 * pop;
        const arc = (1 - pop) * -3;
        const rise = (1 - pop) * 16;
        const opacity = interpolate(wordFrame, [0, 8], [0, 1], {
          easing: EASE_OUT,
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
        const money = word.match(/^\$(\d+)(.*)$/);
        let content: React.ReactNode = word;
        let squashX = 1;
        let squashY = 1;
        if (money) {
          const target = parseInt(money[1], 10);
          const count = Math.round(
            interpolate(wordFrame, [0, 36], [0, target], {
              easing: EASE_OUT,
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            }),
          );
          content = `$${count}${money[2]}`;
          const land = interpolate(wordFrame, [36, 48], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
          const sq = Math.sin(land * Math.PI);
          squashX = 1 + 0.06 * sq;
          squashY = 1 - 0.06 * sq;
        }
        return (
          <span
            key={i}
            style={{
              display: "inline-block",
              transform: `translateY(${rise}px) rotate(${arc}deg) scale(${scale * squashX}, ${scale * squashY})`,
              opacity,
              marginRight: i < words.length - 1 ? 24 : 0,
              color: money ? AMBER : undefined,
            }}
          >
            {content}
          </span>
        );
      })}
    </>
  );
};

// The total slams in and counts 0 → 49 on an eased curve, then squashes as
// it settles. Same final text as the script: "Total: $49/mo".
const TotalLine: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const target = parseInt(text.match(/\$(\d+)/)?.[1] ?? "49", 10);
  const s = spring({
    frame,
    fps,
    config: { damping: 9, stiffness: 240, mass: 0.9 },
  });
  const count = Math.round(
    interpolate(frame, [0, 24], [0, target], {
      easing: EASE_OUT,
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }),
  );
  const base = 2.2 - 1.2 * s;
  const settle = interpolate(s, [0.85, 1], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const bump = Math.sin(settle * Math.PI);
  const opacity = interpolate(frame, [0, 5], [0, 1], {
    easing: EASE_OUT,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div
      style={{
        opacity,
        transform: `scale(${base * (1 + 0.05 * bump)}, ${base * (1 - 0.05 * bump)})`,
        fontSize: 118,
        fontWeight: 600,
        color: AMBER,
        textAlign: "center",
        fontVariantNumeric: "tabular-nums",
      }}
    >
      Total: ${count}/mo
    </div>
  );
};

// Drawn check — one stroke, one size, white. No glyph, no emoji.
const Check: React.FC = () => (
  <svg
    width={44}
    height={44}
    viewBox="0 0 44 44"
    style={{ flexShrink: 0, marginRight: 16, marginTop: 8 }}
  >
    <path
      d="M8 23 L18 33 L37 12"
      fill="none"
      stroke={WHITE}
      strokeWidth={6}
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

// Burned-in caption bar. Ads need captions (most viewers watch muted) —
// this is the explicit exception to the clipsdaily no-captions rule, which
// covers clips, not ads. Text comes from the same script.json beat.
const CaptionBar: React.FC<{ plan: BeatPlan[] }> = ({ plan }) => {
  const frame = useCurrentFrame();
  const beat =
    plan.find((b) => frame >= b.startFrame && frame < b.startFrame + b.frames) ??
    plan[plan.length - 1];
  return (
    <div
      style={{
        position: "absolute",
        left: 64,
        right: 64,
        bottom: 88,
        display: "flex",
        justifyContent: "center",
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          backgroundColor: "rgba(0,0,0,0.62)",
          borderRadius: 16,
          padding: "20px 32px",
          fontFamily: FONT,
          fontSize: 42,
          fontWeight: 600,
          lineHeight: 1.25,
          color: WHITE,
          textAlign: "center",
        }}
      >
        {beat.text}
      </div>
    </div>
  );
};

const sceneLabel = (text: string) => (
  <div
    style={{
      fontFamily: FONT,
      fontSize: 40,
      fontWeight: 600,
      letterSpacing: 2,
      color: MUTED,
    }}
  >
    {text}
  </div>
);

export const ReceiptReel: React.FC<ReceiptReelProps> = ({ script }) => {
  const { fps } = useVideoConfig();
  const plan = getBeatPlan(script, fps);
  const byId = (id: string) => plan.find((b) => b.id === id)!;

  const hook = byId("hook");
  const receiptBeats = plan.filter(
    (b) => b.kind === "receipt" || b.kind === "total",
  );
  const receiptSceneStart = receiptBeats[0].startFrame;
  const receiptSceneEnd =
    receiptBeats[receiptBeats.length - 1].startFrame +
    receiptBeats[receiptBeats.length - 1].frames;
  const altBeats = plan.filter((b) => b.kind === "alternative");
  const altSceneStart = altBeats[0].startFrame;
  const altSceneEnd =
    altBeats[altBeats.length - 1].startFrame +
    altBeats[altBeats.length - 1].frames;
  const cta = byId("cta");

  return (
    <AbsoluteFill style={{ backgroundColor: BG, fontFamily: FONT }}>
      {/* animated endless-runner background, whole reel */}
      <RunnerBackground />

      {/* ---- HOOK (0–3s) ---- */}
      <Sequence from={hook.startFrame} durationInFrames={hook.frames}>
        <Audio src={staticFile(`voiceover/${hook.id}.wav`)} />
        <AbsoluteFill
          style={{
            justifyContent: "center",
            alignItems: "center",
            padding: 72,
          }}
        >
          <div
            style={{
              fontSize: 108,
              fontWeight: 600,
              lineHeight: 1.12,
              color: WHITE,
              textAlign: "center",
            }}
          >
            <HookWords text={hook.text} />
          </div>
        </AbsoluteFill>
      </Sequence>

      {/* ---- RECEIPT (bill lines accumulate, then the total) ---- */}
      <Sequence
        from={receiptSceneStart}
        durationInFrames={receiptSceneEnd - receiptSceneStart}
      >
        <div
          style={{
            position: "absolute",
            top: 112,
            left: 0,
            right: 0,
            display: "flex",
            justifyContent: "center",
          }}
        >
          {sceneLabel("The bill")}
        </div>
        {receiptBeats.map((beat, i) => {
          const isTotal = beat.kind === "total";
          const [left, right] = beat.text.split(" — ");
          return (
            <Sequence
              key={beat.id}
              from={beat.startFrame - receiptSceneStart}
              durationInFrames={receiptSceneEnd - beat.startFrame}
            >
              <Audio src={staticFile(`voiceover/${beat.id}.wav`)} />
              <div
                style={{
                  position: "absolute",
                  top: isTotal ? 1120 : 400 + i * 148,
                  left: 72,
                  right: 72,
                }}
              >
                {isTotal ? (
                  <TotalLine text={beat.text} />
                ) : (
                  <Line
                    kind="slide"
                    enterAt={(i % 3) * 2}
                    style={{
                      backgroundColor: PANEL,
                      border: `1px solid ${PANEL_LINE}`,
                      borderRadius: 16,
                      padding: "32px 40px",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      fontSize: 62,
                      fontWeight: 600,
                      color: WHITE,
                      fontVariantNumeric: "tabular-nums",
                    }}
                  >
                    {right ? (
                      <>
                        <span>{left}</span>
                        <span style={{ color: WHITE, whiteSpace: "nowrap" }}>
                          {right}
                        </span>
                      </>
                    ) : (
                      renderMoney(beat.text)
                    )}
                  </Line>
                )}
              </div>
            </Sequence>
          );
        })}
      </Sequence>

      {/* ---- ALTERNATIVE (ClipForge pitch lines accumulate) ---- */}
      <Sequence
        from={altSceneStart}
        durationInFrames={altSceneEnd - altSceneStart}
      >
        <div
          style={{
            position: "absolute",
            top: 112,
            left: 0,
            right: 0,
            display: "flex",
            justifyContent: "center",
          }}
        >
          <div
            style={{
              fontFamily: FONT,
              fontSize: 52,
              fontWeight: 600,
              letterSpacing: 0,
              color: WHITE,
            }}
          >
            ClipForge
          </div>
        </div>
        {altBeats.map((beat, i) => (
          <Sequence
            key={beat.id}
            from={beat.startFrame - altSceneStart}
            durationInFrames={altSceneEnd - beat.startFrame}
          >
            <Audio src={staticFile(`voiceover/${beat.id}.wav`)} />
            <div
              style={{
                position: "absolute",
                top: 480 + i * 208,
                left: 72,
                right: 72,
              }}
            >
              <Line
                enterAt={i * 2}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  fontSize: 56,
                  fontWeight: 600,
                  lineHeight: 1.25,
                  color: WHITE,
                }}
              >
                <Check />
                <span>{renderMoney(beat.text)}</span>
              </Line>
            </div>
          </Sequence>
        ))}
      </Sequence>

      {/* ---- CTA (hold to the end) ---- */}
      <Sequence from={cta.startFrame} durationInFrames={cta.frames}>
        <Audio src={staticFile(`voiceover/${cta.id}.wav`)} />
        <AbsoluteFill
          style={{
            justifyContent: "center",
            alignItems: "center",
            padding: 72,
          }}
        >
          <div>
            <Line
              style={{
                fontSize: 64,
                fontWeight: 600,
                color: WHITE,
                textAlign: "center",
              }}
            >
              Comment
            </Line>
            <Line
              enterAt={8}
              kind="slam"
              style={{
                fontSize: 132,
                fontWeight: 600,
                color: AMBER,
                textAlign: "center",
                lineHeight: 1.1,
              }}
            >
              CLIPFORGE
            </Line>
            {cta.subtext ? (
              <Line
                enterAt={16}
                style={{
                  fontSize: 58,
                  fontWeight: 600,
                  color: WHITE,
                  textAlign: "center",
                  marginTop: 32,
                }}
              >
                {cta.subtext}
              </Line>
            ) : null}
          </div>
        </AbsoluteFill>
      </Sequence>

      {/* burned-in captions, whole video */}
      <CaptionBar plan={plan} />
    </AbsoluteFill>
  );
};
