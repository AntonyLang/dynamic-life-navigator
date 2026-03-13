import "../../test/setup";

import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DevPanel } from "./DevPanel";

describe("DevPanel", () => {
  it("submits reset values as numbers", async () => {
    const user = userEvent.setup();
    const onResetState = vi.fn().mockResolvedValue(undefined);

    render(
      <DevPanel
        open
        onToggle={vi.fn()}
        onResetState={onResetState}
        onCreateNode={vi.fn()}
        lastDebugEvent={null}
        debugEvents={[]}
        busy={false}
      />,
    );

    await user.clear(screen.getByLabelText("Mental energy"));
    await user.type(screen.getByLabelText("Mental energy"), "61");
    await user.clear(screen.getByLabelText("Physical energy"));
    await user.type(screen.getByLabelText("Physical energy"), "34");
    await user.clear(screen.getByLabelText("Reason"));
    await user.type(screen.getByLabelText("Reason"), "manual rebalance");
    await user.click(screen.getByRole("button", { name: "Submit reset" }));

    expect(onResetState).toHaveBeenCalledWith({
      mental_energy: 61,
      physical_energy: 34,
      reason: "manual rebalance",
    });
  });

  it("parses node creation form fields into backend payload shape", async () => {
    const user = userEvent.setup();
    const onCreateNode = vi.fn().mockResolvedValue(undefined);

    render(
      <DevPanel
        open
        onToggle={vi.fn()}
        onResetState={vi.fn()}
        onCreateNode={onCreateNode}
        lastDebugEvent={null}
        debugEvents={[]}
        busy={false}
      />,
    );

    await user.selectOptions(screen.getByLabelText("Drive type"), "value");
    await user.type(screen.getByLabelText("Title"), "Protect focus hours");
    await user.type(screen.getByLabelText("Summary"), "Set a clearer afternoon boundary.");
    await user.type(screen.getByLabelText("Tags"), "focus, boundary");
    await user.type(screen.getByLabelText("Priority score"), "7");
    await user.type(screen.getByLabelText("Dynamic urgency"), "5");
    await user.type(screen.getByLabelText("Estimated minutes"), "20");
    fireEvent.change(screen.getByLabelText("DDL timestamp"), { target: { value: "2026-03-13T10:30" } });
    await user.click(screen.getByRole("button", { name: "Create node" }));

    expect(onCreateNode).toHaveBeenCalledWith({
      drive_type: "value",
      title: "Protect focus hours",
      summary: "Set a clearer afternoon boundary.",
      tags: ["focus", "boundary"],
      priority_score: 7,
      dynamic_urgency_score: 5,
      estimated_minutes: 20,
      ddl_timestamp: new Date("2026-03-13T10:30").toISOString(),
    });
  });
});
