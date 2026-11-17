import React from "react";
import {
  AbsoluteFill,
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

// Beat length = generated voiceover length (+0.5s tail, baked into `timings`
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
// ---------------------------------------------------------------------------
const BG = "#0B0E11";
const PANEL = "#141A20";
const WHITE = "#FFFFFF";
const MUTED = "#9AA5B1";
const AMBER = "#F5B942";
const CORAL = "#E04A3A";
const FONT = "Arial, Helvetica, sans-serif";

// Background palette — dark and muted on purpose, so the game layer never
// fights the copy. The scrim below does the rest.
const SKY_FAR = "#131B24";
const SKY_MID = "#18222E";
const GROUND = "#0C1117";
const GROUND_EDGE = "#1D2833";
const LANE = "#22303C";
const RUNNER = "#37454F";

// Money amounts ($49/mo, $19–29/mo, $199) always render amber.
const MONEY_RE = /(\$[0-9][0-9.,–-]*(?:\/mo)?)/g;

function renderMoney(text: string): React.ReactNode {
  return text.split(MONEY_RE).map((part, i) =>
    MONEY_RE.test(part) || /^\$/.test(part) ? (
      <span key={i} style={{ color: AMBER }}>
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

// ---------------------------------------------------------------------------
// Animated background — endless-runner scene, drawn entirely in code.
// No ripped footage, no copyrighted assets. Layers (slow → fast):
// stars → far skyline → mid skyline (lit windows) → ground + lane dashes
// → scrim → runner silhouette + coins + speed lines (above the scrim so
// the motion still reads, but small and dim enough to stay out of the
// copy's way). All copy sits on opaque panels, the caption pill, or the
// scrim — legibility is structural, not luck.
// ---------------------------------------------------------------------------
type Building = {
  x: number;
  w: number;
  h: number;
  windows: { dx: number; dy: number }[];
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
    const windows: { dx: number; dy: number }[] = [];
    if (withWindows) {
      for (let k = 0; k < 3; k++) {
        windows.push({
          dx: 12 + rand(seedBase + i * 17 + k * 5) * Math.max(10, w - 26),
          dy: 18 + rand(seedBase + i * 17 + k * 5 + 1) * Math.max(10, h - 50),
        });
      }
    }
    buildings.push({ x, w, h, windows });
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

const SPEED_LINES = Array.from({ length: 10 }, (_, i) => ({
  x0: rand(700 + i * 11) * 1300,
  y: 160 + rand(700 + i * 11 + 1) * 1550,
  len: 80 + rand(700 + i * 11 + 2) * 130,
  speed: 12 + rand(700 + i * 11 + 3) * 7,
  o: 0.04 + rand(700 + i * 11 + 4) * 0.05,
}));

const COINS_TOP = Array.from({ length: 5 }, (_, i) => ({
  x0: i * 260 + rand(300 + i) * 80,
  y: 322,
  speed: 6,
}));

const COINS_GROUND = Array.from({ length: 6 }, (_, i) => ({
  x0: i * 240 + rand(400 + i) * 60,
  y: 1510,
  speed: 9,
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
            {b.windows.map((wn, j) => (
              <div
                key={j}
                style={{
                  position: "absolute",
                  left: wn.dx,
                  top: wn.dy,
                  width: 7,
                  height: 9,
                  borderRadius: 2,
                  backgroundColor: AMBER,
                  opacity: 0.28,
                }}
              />
            ))}
          </div>
        ))}
      </div>
    ))}
  </>
);

// Simple geometric runner silhouette — thick round-capped limbs, legs and
// arms swinging in opposite phase, small hop on each stride. Abstract on
// purpose: it reads as motion at small size without pretending to be art.
const RunnerFigure: React.FC<{ frame: number }> = ({ frame }) => {
  const t = frame * 0.34;
  const bob = -Math.abs(Math.sin(t)) * 12;
  const legSwing = Math.sin(t) * 40;
  const armSwing = Math.sin(t + Math.PI) * 34;
  return (
    <svg
      width={170}
      height={230}
      viewBox="0 0 170 230"
      style={{ overflow: "visible" }}
    >
      <g transform={`translate(85, 8) rotate(7) translate(0, ${bob})`}>
        <circle cx={4} cy={16} r={15} fill={RUNNER} />
        <line
          x1={0}
          y1={34}
          x2={-8}
          y2={102}
          stroke={RUNNER}
          strokeWidth={22}
          strokeLinecap="round"
        />
        <line
          x1={-2}
          y1={48}
          x2={-38}
          y2={84}
          stroke={RUNNER}
          strokeWidth={13}
          strokeLinecap="round"
          transform={`rotate(${-armSwing} -2 48)`}
        />
        <line
          x1={-2}
          y1={48}
          x2={34}
          y2={88}
          stroke={RUNNER}
          strokeWidth={13}
          strokeLinecap="round"
          transform={`rotate(${armSwing} -2 48)`}
        />
        <line
          x1={-8}
          y1={102}
          x2={-44}
          y2={168}
          stroke={RUNNER}
          strokeWidth={15}
          strokeLinecap="round"
          transform={`rotate(${-legSwing} -8 102)`}
        />
        <line
          x1={-8}
          y1={102}
          x2={40}
          y2={172}
          stroke={RUNNER}
          strokeWidth={15}
          strokeLinecap="round"
          transform={`rotate(${legSwing} -8 102)`}
        />
      </g>
    </svg>
  );
};

const RunnerBackground: React.FC = () => {
  const frame = useCurrentFrame();
  const farX = -(mod(frame * 1.2, FAR.width));
  const midX = -(mod(frame * 3.5, MID.width));
  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      {/* sky */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "linear-gradient(180deg, #0B0E11 0%, #0E141B 55%, #111A22 100%)",
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
      {/* skylines, parallax */}
      <SkylineLayer data={FAR} color={SKY_FAR} offset={farX} />
      <SkylineLayer data={MID} color={SKY_MID} offset={midX} />
      {/* ground + lane dashes, fast */}
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
            width: 90,
            height: 8,
            borderRadius: 4,
            backgroundColor: LANE,
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
          left: 140,
          top: 1360,
          opacity: 0.95,
        }}
      >
        <RunnerFigure frame={frame} />
      </div>
      {/* coins — two lanes, spin as they scroll */}
      {[...COINS_TOP, ...COINS_GROUND].map((c, i) => {
        const x = mod(c.x0 - frame * c.speed, 1240) - 80;
        const spin = Math.abs(Math.cos(frame * 0.12 + i * 1.3));
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: x,
              top: c.y,
              width: 34,
              height: 34,
              borderRadius: "50%",
              background:
                "radial-gradient(circle at 35% 35%, #FFD97A, #F5B942 60%, #C98A1B)",
              opacity: 0.8,
              transform: `scaleX(${0.35 + 0.65 * spin})`,
            }}
          />
        );
      })}
      {/* speed lines */}
      {SPEED_LINES.map((l, i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            left: mod(l.x0 - frame * l.speed, 1400) - 160,
            top: l.y,
            width: l.len,
            height: 3,
            borderRadius: 2,
            backgroundColor: WHITE,
            opacity: l.o,
          }}
        />
      ))}
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// Kinetic text.
// - "fade": the v2 entrance (opacity + rise). Alt lines keep this.
// - "slide": receipt rows slide in from the right, one per beat.
// - "slam": the total scales down hard with an overshoot settle.
// NOTE: useCurrentFrame() is relative to the NEAREST <Sequence>, so `enterAt`
// is the offset inside this line's own Sequence (0 for lines whose Sequence
// starts exactly at their beat). Do NOT pass a global frame here — that
// double-subtracts and the line never appears.
// ---------------------------------------------------------------------------
const Line: React.FC<{
  enterAt?: number;
  kind?: "fade" | "slide" | "slam";
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({ enterAt = 0, kind = "fade", children, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const local = Math.max(0, frame - enterAt);
  const opacity = interpolate(local, [0, kind === "slam" ? 5 : 10], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  let transform = "";
  if (kind === "fade") {
    const y = interpolate(local, [0, 12], [28, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    transform = `translateY(${y}px)`;
  } else if (kind === "slide") {
    const s = spring({
      frame: local,
      fps,
      config: { damping: 15, stiffness: 200, mass: 0.8 },
    });
    transform = `translateX(${(1 - s) * 200}px)`;
  } else {
    const s = spring({
      frame: local,
      fps,
      config: { damping: 8, stiffness: 260, mass: 0.9 },
    });
    transform = `scale(${1.8 - 0.8 * s})`;
  }
  return (
    <div style={{ opacity, transform, ...style }}>{children}</div>
  );
};

// Hook words pop in one at a time; the $49 counts up 0 → 49 as its word
// lands. Money words stay amber; everything else stays white.
const HookWords: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const words = text.split(" ");
  return (
    <>
      {words.map((word, i) => {
        const wordFrame = Math.max(0, frame - i * 5);
        const pop = spring({
          frame: wordFrame,
          fps,
          config: { damping: 12, stiffness: 300, mass: 0.7 },
        });
        const scale = 0.45 + 0.55 * pop;
        const opacity = interpolate(wordFrame, [0, 8], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
        const money = word.match(/^\$(\d+)(.*)$/);
        let content: React.ReactNode = word;
        if (money) {
          const target = parseInt(money[1], 10);
          const count = Math.round(
            interpolate(wordFrame, [0, 36], [0, target], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            }),
          );
          content = `$${count}${money[2]}`;
        }
        return (
          <span
            key={i}
            style={{
              display: "inline-block",
              transform: `scale(${scale})`,
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
        left: 60,
        right: 60,
        bottom: 90,
        display: "flex",
        justifyContent: "center",
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          backgroundColor: "rgba(0,0,0,0.62)",
          borderRadius: 18,
          padding: "22px 34px",
          fontFamily: FONT,
          fontSize: 42,
          fontWeight: 700,
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
      fontSize: 44,
      fontWeight: 900,
      letterSpacing: 10,
      color: MUTED,
    }}
  >
    {text}
  </div>
);

export const ReceiptReel: React.FC<ReceiptReelProps> = ({ script }) => {
  const { fps } = useVideoConfig();
  const frame = useCurrentFrame();
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

  // CTA pulse while held — gentle, 1.4s period, ±3%.
  const ctaPulse = 1 + 0.03 * Math.sin(frame * 0.14);

  return (
    <AbsoluteFill style={{ backgroundColor: BG, fontFamily: FONT }}>
      {/* animated endless-runner background, whole reel */}
      <RunnerBackground />

      {/* top accent bar */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: 12,
          backgroundColor: AMBER,
        }}
      />

      {/* ---- HOOK (0–3s) ---- */}
      <Sequence from={hook.startFrame} durationInFrames={hook.frames}>
        <Audio src={staticFile(`voiceover/${hook.id}.wav`)} />
        <AbsoluteFill
          style={{
            justifyContent: "center",
            alignItems: "center",
            padding: 70,
          }}
        >
          <div
            style={{
              fontSize: 108,
              fontWeight: 900,
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
            top: 110,
            left: 0,
            right: 0,
            display: "flex",
            justifyContent: "center",
          }}
        >
          {sceneLabel("THE BILL")}
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
                  top: isTotal ? 1180 : 330 + i * 150,
                  left: 70,
                  right: 70,
                }}
              >
                <Line
                  kind={isTotal ? "slam" : "slide"}
                  style={
                    isTotal
                      ? {
                          fontSize: 118,
                          fontWeight: 900,
                          color: AMBER,
                          textAlign: "center",
                        }
                      : {
                          backgroundColor: PANEL,
                          borderRadius: 20,
                          padding: "34px 40px",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          fontSize: 62,
                          fontWeight: 800,
                          color: WHITE,
                        }
                  }
                >
                  {right ? (
                    <>
                      <span>{left}</span>
                      <span style={{ color: CORAL, whiteSpace: "nowrap" }}>
                        {right}
                      </span>
                    </>
                  ) : (
                    renderMoney(beat.text)
                  )}
                </Line>
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
            top: 110,
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
              fontWeight: 900,
              letterSpacing: 6,
              color: AMBER,
            }}
          >
            CLIPFORGE
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
                top: 430 + i * 210,
                left: 70,
                right: 70,
              }}
            >
              <Line
                style={{
                  fontSize: 60,
                  fontWeight: 800,
                  lineHeight: 1.25,
                  color: WHITE,
                }}
              >
                <span style={{ color: AMBER }}>✓ </span>
                {renderMoney(beat.text)}
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
            padding: 70,
          }}
        >
          <div style={{ transform: `scale(${ctaPulse})` }}>
            <Line
              style={{
                fontSize: 64,
                fontWeight: 800,
                color: WHITE,
                textAlign: "center",
              }}
            >
              Comment
            </Line>
            <Line
              enterAt={8}
              style={{
                fontSize: 132,
                fontWeight: 900,
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
                  fontWeight: 700,
                  color: WHITE,
                  textAlign: "center",
                  marginTop: 30,
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
