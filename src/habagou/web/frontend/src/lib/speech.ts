import { useCallback, useEffect, useState } from "react";

// Click-to-hear pronunciation via the browser's built-in Web Speech API. Chinese
// text is spoken with a zh-CN (Mandarin) voice, so tones follow from the hanzi
// itself — no audio assets or backend calls. Devices without a Chinese voice
// (some desktops/Linux) simply report unsupported and the UI hides the control.

const CHINESE_LANG = "zh-CN";
// A touch slower than natural pace so learners can hear each syllable.
const LEARNER_RATE = 0.85;

function normalizeLang(lang: string): string {
  return lang.replace("_", "-").toLowerCase();
}

export function isSpeechSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "speechSynthesis" in window &&
    typeof window.SpeechSynthesisUtterance !== "undefined"
  );
}

// Prefer a mainland-Mandarin (zh-CN) voice, then any Chinese voice. Returns null
// when the device ships no Chinese voice at all.
export function pickChineseVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
  const chinese = voices.filter((voice) => normalizeLang(voice.lang).startsWith("zh"));
  if (chinese.length === 0) {
    return null;
  }
  return (
    chinese.find((voice) => normalizeLang(voice.lang) === "zh-cn") ??
    chinese.find((voice) => normalizeLang(voice.lang).startsWith("zh-cn")) ??
    chinese[0]
  );
}

export type UseSpeak = {
  supported: boolean;
  speaking: boolean;
  speak: (text: string) => void;
};

export function useSpeak(): UseSpeak {
  // Lazy init so the check runs once and is stable across renders.
  const [supported] = useState(isSpeechSupported);
  const [speaking, setSpeaking] = useState(false);

  // Voices load asynchronously in some browsers; warm the list and refresh it
  // when the engine signals it is ready. Also stop any speech on unmount.
  useEffect(() => {
    if (!supported) {
      return;
    }
    const synth = window.speechSynthesis;
    synth.getVoices();
    const handler = () => synth.getVoices();
    synth.addEventListener?.("voiceschanged", handler);
    return () => {
      synth.removeEventListener?.("voiceschanged", handler);
      synth.cancel();
    };
  }, [supported]);

  const speak = useCallback(
    (text: string) => {
      if (!supported || !text) {
        return;
      }
      const synth = window.speechSynthesis;
      synth.cancel(); // interrupt any in-flight utterance
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = CHINESE_LANG;
      utterance.rate = LEARNER_RATE;
      const voice = pickChineseVoice(synth.getVoices());
      if (voice) {
        utterance.voice = voice;
      }
      utterance.onstart = () => setSpeaking(true);
      utterance.onend = () => setSpeaking(false);
      utterance.onerror = () => setSpeaking(false);
      synth.speak(utterance);
    },
    [supported],
  );

  return { supported, speaking, speak };
}
