import React from "react";
import {
  AbsoluteFill,
  interpolate,
  Sequence,
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

// Fade + rise entrance for a line.
// NOTE: useCurrentFrame() is relative to the NEAREST <Sequence>, so `enterAt`
// is the offset inside this line's own Sequence (0 for lines whose Sequence
// starts exactly at their beat). Do NOT pass a global frame here — that
// double-subtracts and the line never appears.
const Line: React.FC<{
  enterAt?: number;
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({ enterAt = 0, children, style }) => {
  const frame = useCurrentFrame();
  const local = frame - enterAt;
  const opacity = interpolate(local, [0, 12], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const y = interpolate(local, [0, 12], [28, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div style={{ opacity, translate: `0px ${y}px`, ...style }}>{children}</div>
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
          <Line
            style={{
              fontSize: 108,
              fontWeight: 900,
              lineHeight: 1.12,
              color: WHITE,
              textAlign: "center",
            }}
          >
            {renderMoney(hook.text)}
          </Line>
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
        </AbsoluteFill>
      </Sequence>

      {/* burned-in captions, whole video */}
      <CaptionBar plan={plan} />
    </AbsoluteFill>
  );
};
