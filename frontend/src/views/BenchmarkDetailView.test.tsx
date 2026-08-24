import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { catalogApi } from "@/lib/api/catalog";
import { evaluationsApi } from "@/lib/api/evaluations";
import type { Evaluation } from "@/lib/api/evaluations.types";
import BenchmarkDetailView from "@/views/BenchmarkDetailView";

vi.mock("@/lib/preferencesContext", () => ({
  usePreferences: () => ({
    preferences: { hide_closed_source_evals: false },
    setHideClosedSourceEvals: vi.fn(),
  }),
}));

const Location = () => <output data-testid="location">{useLocation().search}</output>;

function evaluation(overrides: Partial<Evaluation> = {}): Evaluation {
  return {
    id: "1",
    paper_id: "paper-1",
    task_id: "task-1",
    dataset_id: "dataset-1",
    model_name: "Model One",
    metrics: { Accuracy: 90 },
    uses_additional_data: false,
    is_open: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function setup(known = 2) {
  vi.spyOn(catalogApi, "getDatasetBySlug").mockResolvedValue({
    id: "dataset-1",
    name: "Test benchmark",
    slug: "test-benchmark",
  });
  vi.spyOn(catalogApi, "datasetTasks").mockResolvedValue([
    { id: "task-1", name: "Test task", slug: "test-task", level: 0 },
  ]);
  vi.spyOn(catalogApi, "metricDirections").mockResolvedValue({
    directions: { Accuracy: "higher_is_better" },
  });
  vi.spyOn(catalogApi, "leaderboardMetrics").mockResolvedValue([
    { metric_id: "metric-1", metric_name: "Accuracy", metric_direction: "higher_is_better" },
  ]);
  vi.spyOn(catalogApi, "trendingBenchmarks").mockResolvedValue({ results: [] } as never);
  vi.spyOn(evaluationsApi, "byDataset").mockResolvedValue([
    evaluation({ id: "first", model_name: "First", num_parameters: 1_234_567_890 }),
    evaluation({ id: "second", paper_id: "paper-2", model_name: "Second", num_parameters: 2_000_000_000 }),
  ]);
  vi.spyOn(evaluationsApi, "list").mockResolvedValue({
    count: 2,
    next_page: null,
    previous_page: null,
    results: [],
    parameter_coverage_known: known,
    parameter_coverage_total: 2,
  });
  return vi.spyOn(evaluationsApi, "byLeaderboard").mockResolvedValue([]);
}

function renderView(path = "/datasets/test-benchmark") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/datasets/:datasetSlug" element={<><BenchmarkDetailView /><Location /></>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("BenchmarkDetailView parameter filters", () => {
  it("updates the table, SOTA chart, and headline best model together", async () => {
    const smallOne = evaluation({
      id: "small-one",
      model_name: "Small One",
      metrics: { Accuracy: 80 },
      num_parameters: 400_000_000,
      paper_published_date: "2025-01-15",
    });
    const smallTwo = evaluation({
      id: "small-two",
      paper_id: "paper-2",
      model_name: "Small Two",
      metrics: { Accuracy: 90 },
      num_parameters: 800_000_000,
      paper_published_date: "2025-02-15",
    });
    const largeBest = evaluation({
      id: "large-best",
      paper_id: "paper-3",
      model_name: "Large Best",
      metrics: { Accuracy: 99 },
      num_parameters: 5_000_000_000,
      paper_published_date: "2025-03-15",
    });
    const filtered = setup(3);
    vi.mocked(evaluationsApi.byDataset).mockResolvedValue([smallOne, smallTwo, largeBest]);
    filtered.mockResolvedValue([smallOne, smallTwo]);

    renderView("/datasets/test-benchmark?max_parameters_exclusive=1000000000");

    expect(await screen.findByRole("button", { name: "<1B" })).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByText("Small Two", { selector: ".best-name" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Small One: 80/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Small Two: 90/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Large Best: 99/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "All" }));

    expect(await screen.findByText("Large Best", { selector: ".best-name" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Large Best: 99/ })).toBeInTheDocument();
    expect(await screen.findByTestId("location")).toHaveTextContent("");
  });

  it("keeps the chart visible when a parameter filter leaves one model", async () => {
    const onlyMatch = evaluation({
      id: "only-match",
      model_name: "Only Match",
      metrics: { Accuracy: 88 },
      num_parameters: 800_000_000,
      paper_published_date: "2025-02-15",
    });
    const filtered = setup();
    filtered.mockResolvedValue([onlyMatch]);

    renderView("/datasets/test-benchmark?max_parameters_exclusive=1000000000");

    expect(await screen.findByText("Only Match", { selector: ".best-name" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Only Match: 88/ })).toBeInTheDocument();
  });

  it("loads a URL-selected bound through the API, reports coverage, reranks ties, and clears an empty filter", async () => {
    const filtered = setup();
    renderView("/datasets/test-benchmark?max_parameters_exclusive=1000000000");

    expect(await screen.findByText("Parameters known for 2 of 2 entries")).toBeInTheDocument();
    expect(filtered).toHaveBeenCalledWith("dataset-1", "task-1", {
      is_open: undefined,
      max_parameters_exclusive: 1_000_000_000,
    });
    expect(await screen.findByText(/No known parameter counts match this filter/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show all" }));
    expect(await screen.findByTestId("location")).toHaveTextContent("");
    expect(await screen.findByText("1.23B")).toHaveAttribute("aria-label", "1,234,567,890 parameters");
    expect(screen.getAllByText("1", { selector: ".col-rank" })).toHaveLength(2);
  });

  it("reports a filtered leaderboard request failure instead of an empty result", async () => {
    const filtered = setup();
    filtered.mockRejectedValue(new Error("network unavailable"));

    renderView("/datasets/test-benchmark?max_parameters_exclusive=1000000000");

    expect(await screen.findByText("Failed to filter evaluations by parameter size.")).toBeInTheDocument();
    expect(screen.queryByText(/No known parameter counts match this filter/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Loading benchmark summary")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(filtered).toHaveBeenCalledTimes(2);
  });

  it("hides controls when no displayed entry has known parameter metadata", async () => {
    setup(0);
    renderView();

    expect(await screen.findByText("Parameter metadata unavailable")).toBeInTheDocument();
    expect(screen.queryByText(/Parameters known for/)).not.toBeInTheDocument();
  });
});
