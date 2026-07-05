import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Button } from "@/components/ui/Button";

describe("Button", () => {
  it("defaults to a non-submitting button and handles activation", () => {
    const onClick = vi.fn();

    render(<Button onClick={onClick}>Save report</Button>);

    const button = screen.getByRole("button", { name: "Save report" });
    expect(button).toHaveAttribute("type", "button");
    fireEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("supports disabled state", () => {
    render(<Button disabled>Save report</Button>);

    expect(screen.getByRole("button", { name: "Save report" })).toBeDisabled();
  });
});
