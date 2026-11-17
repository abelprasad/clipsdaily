import { Composition } from "remotion";
import { getTotalFrames, ReceiptReel } from "./ReceiptReel";
import type { ReceiptReelProps } from "./ReceiptReel";
import scriptJson from "./script.json";

const defaultScript = scriptJson as unknown as ReceiptReelProps["script"];

export const ReceiptReelComposition = () => {
  return (
    <Composition
      id="ReceiptReel"
      component={ReceiptReel}
      fps={30}
      width={1080}
      height={1920}
      durationInFrames={getTotalFrames(defaultScript, 30)}
      defaultProps={{ script: defaultScript }}
      calculateMetadata={({ props }) => {
        return {
          durationInFrames: getTotalFrames(props.script, 30),
        };
      }}
    />
  );
};
