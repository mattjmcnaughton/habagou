import type { ChatModelOption } from "../lib/api";

// Admin-only AI model chip row, shared by the two AI chats (pack generation
// and practice). Rendered only when the status endpoint returned a models
// list with a real choice (>= 2 entries) — the server sends the list to admin
// callers only, so the status response itself gates this UI. A `selected` of
// undefined means the server default (its chip renders active); clicking the
// default chip clears the override so "selection = default" always means a
// model-free request body.
export function ModelPicker({
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
  return (
    <div className="flex flex-wrap items-center gap-2 border-t border-white/10 px-4 pt-3">
      <span className="text-xs font-semibold uppercase tracking-[0.16em] text-mist">Model</span>
      {models.map((option) => {
        const active = selected === undefined ? option.id === defaultModel : option.id === selected;
        return (
          <button
            aria-pressed={active}
            className={`rounded-full border px-3 py-1 text-xs font-semibold transition-colors disabled:opacity-40 ${
              active
                ? "border-jade/40 bg-jade/10 text-jade"
                : "border-white/10 text-mist hover:border-white/25 hover:text-porcelain"
            }`}
            disabled={disabled}
            key={option.id}
            onClick={() => onSelect(option.id === defaultModel ? undefined : option.id)}
            type="button"
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
