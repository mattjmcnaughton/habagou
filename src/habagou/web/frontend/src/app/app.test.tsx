import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "./app";

describe("App", () => {
  it("renders the routed home shell", async () => {
    render(<App />);

    expect(await screen.findByRole("heading", { name: "Habagou" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Choose a pack" })).toBeTruthy();
    expect(screen.getByText("哈巴狗")).toBeTruthy();
    expect(screen.getByText("Greetings")).toBeTruthy();
  });
});
