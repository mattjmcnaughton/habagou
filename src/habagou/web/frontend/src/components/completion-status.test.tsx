import type { UseMutationResult } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CompletionStatus } from "./completion-status";

describe("CompletionStatus", () => {
  it("shows a retry action when completion recording fails", () => {
    const mutate = vi.fn();
    const completion = {
      isError: true,
      isPending: false,
      isSuccess: false,
      mutate,
    } as unknown as UseMutationResult<unknown, Error, void, unknown>;

    render(<CompletionStatus completion={completion} />);

    expect(screen.getByRole("alert").textContent).toContain("Completion could not be recorded.");
    fireEvent.click(screen.getByRole("button", { name: "Retry recording" }));
    expect(mutate).toHaveBeenCalledOnce();
  });
});
