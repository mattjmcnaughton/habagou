import { useEffect, useRef, useState } from "react";
import type { ChatModelOption } from "../lib/api";

// Admin-only tutor-model selector shared by the two AI chats (Practice and
// pack generation). Rather than lay every model out as a permanent chip row, it
// collapses the choice into a single pill that lives in the composer and opens a
// bottom sheet on demand — model choice is a rarely-touched power-user setting,
// so it stays quiet until asked for. Rendered only when the status endpoint returned
// a models list with a real choice (>= 2 entries); the server sends that list
// to admin callers only, so the status response itself gates this UI. A
// `selected` of undefined means the server default; picking the default clears
// the override so "selection = default" always means a model-free request body.

// Best-effort provider blurb from the model id prefix (e.g. "openai/gpt…" ->
// "OpenAI"). Always correct even for models this build has never seen: an
// unknown prefix is shown verbatim, and an id without a prefix gets no blurb.
const PROVIDER_LABELS: Record<string, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  minimax: "MiniMax",
  google: "Google",
  "meta-llama": "Meta",
  mistralai: "Mistral",
  deepseek: "DeepSeek",
  "x-ai": "xAI",
};

function providerFor(id: string): string | null {
  const slash = id.indexOf("/");
  if (slash <= 0) {
    return null;
  }
  const key = id.slice(0, slash);
  return PROVIDER_LABELS[key] ?? key;
}

export function ModelSelector({
  defaultModel,
  disabled,
  models,
  onSelect,
  selected,
}: {
  defaultModel: string | null;
  disabled: boolean;
  models: ChatModelOption[];
  onSelect: (model: string | undefined) => void;
  selected: string | undefined;
}) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);

  // The active id resolves an undefined selection to the server default, so the
  // pill always names a concrete model even before the learner touches it.
  const activeId = selected ?? defaultModel;
  const activeLabel =
    models.find((option) => option.id === activeId)?.label ?? models[0]?.label ?? "Default";

  function close() {
    setOpen(false);
    // Restore focus to the pill: closing unmounts the sheet and would otherwise
    // drop focus to <body>.
    triggerRef.current?.focus();
  }

  return (
    <>
      <button
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={`Tutor model: ${activeLabel}`}
        className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-panel2 px-3 py-1.5 text-xs font-semibold text-porcelain transition-colors hover:border-white/25 disabled:opacity-40"
        disabled={disabled}
        onClick={() => setOpen(true)}
        ref={triggerRef}
        type="button"
      >
        <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-jade" />
        <span>{activeLabel}</span>
        <span aria-hidden="true" className="text-mist">
          ⌄
        </span>
      </button>
      {open ? (
        <ModelSheet
          activeId={activeId}
          defaultModel={defaultModel}
          models={models}
          onClose={close}
          onSelect={onSelect}
        />
      ) : null}
    </>
  );
}

function ModelSheet({
  activeId,
  defaultModel,
  models,
  onClose,
  onSelect,
}: {
  activeId: string | null;
  defaultModel: string | null;
  models: ChatModelOption[];
  onClose: () => void;
  onSelect: (model: string | undefined) => void;
}) {
  const [shown, setShown] = useState(false);
  const activeRef = useRef<HTMLButtonElement>(null);

  // Play the entrance on mount and move focus onto the current choice, so a
  // keyboard learner lands inside the sheet rather than back on the trigger.
  useEffect(() => {
    setShown(true);
    activeRef.current?.focus();
  }, []);

  // Escape closes the sheet from anywhere, matching the scrim tap.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex flex-col justify-end">
      <button
        aria-label="Close model picker"
        className={`absolute inset-0 bg-black/55 transition-opacity duration-200 motion-reduce:transition-none ${
          shown ? "opacity-100" : "opacity-0"
        }`}
        onClick={onClose}
        type="button"
      />
      {/* A native <dialog> for correct semantics; `static` + reset utilities
          undo the UA positioning so it lays out as our bottom sheet. */}
      <dialog
        aria-label="Choose tutor model"
        aria-modal="true"
        className={`static m-0 mx-auto block w-full max-w-[440px] rounded-t-3xl border-0 border-t border-white/10 bg-panel2 px-4 pb-8 pt-2.5 text-porcelain shadow-panel transition-all duration-200 motion-reduce:transition-none ${
          shown ? "translate-y-0 opacity-100" : "translate-y-6 opacity-0"
        }`}
        open
      >
        <div aria-hidden="true" className="mx-auto mb-3.5 h-1 w-9 rounded-full bg-white/15" />
        <h2 className="text-base font-bold text-porcelain">Tutor model</h2>
        <p className="mt-0.5 mb-3 text-sm text-mist">
          Switch anytime — your conversation carries over.
        </p>
        <div className="flex flex-col gap-1">
          {models.map((option) => {
            const active = option.id === activeId;
            const provider = providerFor(option.id);
            return (
              <button
                aria-label={option.label}
                aria-pressed={active}
                className={`flex items-center gap-3 rounded-xl border px-3 py-3 text-left transition-colors ${
                  active ? "border-jade/35 bg-jade/10" : "border-transparent hover:bg-white/[0.04]"
                }`}
                key={option.id}
                onClick={() => {
                  // Selecting the default clears the override so the request
                  // body stays model-free; anything else rides the wire.
                  onSelect(option.id === defaultModel ? undefined : option.id);
                  onClose();
                }}
                ref={active ? activeRef : undefined}
                type="button"
              >
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-bold text-porcelain">{option.label}</span>
                  {provider ? <span className="block text-xs text-mist">{provider}</span> : null}
                </span>
                <span
                  aria-hidden="true"
                  className={`text-jade transition-opacity ${active ? "opacity-100" : "opacity-0"}`}
                >
                  ✓
                </span>
              </button>
            );
          })}
        </div>
      </dialog>
    </div>
  );
}
