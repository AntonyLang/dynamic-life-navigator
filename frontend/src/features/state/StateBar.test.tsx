import "../../test/setup";

import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StateBar } from "./StateBar";

describe("StateBar", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows stale state when the query is stale by age", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-03-13T10:01:10Z"));

    render(
      <StateBar
        state={{
          mental_energy: 70,
          physical_energy: 60,
          focus_mode: "deep_work",
          do_not_disturb_until: null,
          recent_context: "planning",
          last_updated_at: "2026-03-13T10:00:00Z",
        }}
        stale={false}
        loading={false}
        errorMessage={null}
        lastSuccessfulAt={new Date("2026-03-13T10:00:00Z").getTime()}
      />,
    );

    expect(screen.getByText("stale")).toBeInTheDocument();
    expect(screen.getByText("Latest successful state refresh is older than 60 seconds.")).toBeInTheDocument();
  });

  it("shows the backend error when the state query fails", () => {
    render(
      <StateBar
        state={null}
        stale
        loading={false}
        errorMessage="Request timed out."
        lastSuccessfulAt={null}
      />,
    );

    expect(screen.getByText("State request failed: Request timed out.")).toBeInTheDocument();
  });
});
