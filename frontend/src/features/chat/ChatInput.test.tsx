import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ChatInput } from "./ChatInput";

describe("ChatInput", () => {
  it("routes /pull to the pull handler", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    const onPull = vi.fn();
    const onBrief = vi.fn();
    const onChange = vi.fn();

    render(
      <ChatInput
        value="/pull"
        onChange={onChange}
        onSend={onSend}
        onPull={onPull}
        onBrief={onBrief}
        onQuickFill={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(onPull).toHaveBeenCalledTimes(1);
    expect(onSend).not.toHaveBeenCalled();
    expect(onBrief).not.toHaveBeenCalled();
  });

  it("routes /brief to the brief handler", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    const onPull = vi.fn();
    const onBrief = vi.fn();

    render(
      <ChatInput
        value="/brief"
        onChange={vi.fn()}
        onSend={onSend}
        onPull={onPull}
        onBrief={onBrief}
        onQuickFill={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(onBrief).toHaveBeenCalledTimes(1);
    expect(onSend).not.toHaveBeenCalled();
    expect(onPull).not.toHaveBeenCalled();
  });

  it("sends normal text through the main send handler", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    const onPull = vi.fn();
    const onBrief = vi.fn();

    render(
      <ChatInput
        value="Need one clear next step."
        onChange={vi.fn()}
        onSend={onSend}
        onPull={onPull}
        onBrief={onBrief}
        onQuickFill={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(onSend).toHaveBeenCalledWith("Need one clear next step.");
    expect(onPull).not.toHaveBeenCalled();
    expect(onBrief).not.toHaveBeenCalled();
  });
});
