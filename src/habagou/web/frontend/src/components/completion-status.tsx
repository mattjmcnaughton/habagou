import type { UseMutationResult } from "@tanstack/react-query";

type CompletionStatusProps<TData> = {
  completion: UseMutationResult<TData, Error, void, unknown>;
};

export function CompletionStatus<TData>({ completion }: CompletionStatusProps<TData>) {
  if (completion.isSuccess) {
    return <p className="mt-4 text-sm text-jade">Completion recorded.</p>;
  }

  if (completion.isError) {
    return (
      <div className="mt-4" role="alert">
        <p className="text-sm text-clay">Completion could not be recorded.</p>
        <button
          className="mt-3 rounded-md border border-clay/40 px-3 py-2 text-sm font-semibold text-porcelain transition-colors hover:bg-clay/10 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={completion.isPending}
          onClick={() => completion.mutate()}
          type="button"
        >
          {completion.isPending ? "Retrying..." : "Retry recording"}
        </button>
      </div>
    );
  }

  return <p className="mt-4 text-sm text-jade">Recording completion...</p>;
}
