import { useEffect, useRef, useState, type DragEvent } from "react";
import { Check, ImagePlus, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useMutation } from "@tanstack/react-query";
import { submitPendingPaperEdit, type PendingEditType } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";

type TaxonomyKind = "task" | "method" | "benchmark" | "metric" | "conference";

interface SuggestTaxonomyDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Omitted for suggestions submitted from a taxonomy directory page. */
  paperId?: string;
  kind: TaxonomyKind;
}

const NAME_MAX = 200;
const DESCRIPTION_MAX = 2000;
const VENUE_MAX = 300;
const URL_MAX = 500;
const IMAGE_SOURCE_MAX = 1000;
const IMAGE_MAX_BYTES = 2 * 1024 * 1024;
const ACCEPTED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"];

interface SuggestionImage {
  file_name: string;
  mime_type: string;
  data_url: string;
}

const KIND_EDIT_TYPE: Record<TaxonomyKind, PendingEditType> = {
  task: "new_task",
  method: "new_method",
  benchmark: "new_benchmark",
  metric: "new_metric",
  conference: "new_conference",
};

const KIND_NAME_PLACEHOLDER: Record<TaxonomyKind, string> = {
  task: "e.g. Long-context Retrieval",
  method: "e.g. Rotary Position Embedding",
  benchmark: "e.g. ImageNet (ReaL)",
  metric: "e.g. Top-5 Accuracy",
  conference: "e.g. International Conference on Machine Learning 2026",
};

const KIND_DESCRIPTION_PLACEHOLDER: Record<TaxonomyKind, string> = {
  task: "Briefly describe this task and what it covers.",
  method: "Briefly describe this method and what it covers.",
  benchmark:
    "Briefly describe this benchmark, the task it belongs to, and where it comes from.",
  metric:
    "Briefly describe this metric and whether higher or lower is better.",
  conference:
    "Briefly describe this conference, including its research focus and edition.",
};

export function SuggestTaxonomyDialog({
  open,
  onOpenChange,
  paperId,
  kind,
}: SuggestTaxonomyDialogProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [year, setYear] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [venue, setVenue] = useState("");
  const [url, setUrl] = useState("");
  const [image, setImage] = useState<SuggestionImage | null>(null);
  const [imageSource, setImageSource] = useState("");
  const [source, setSource] = useState("");
  const [keywords, setKeywords] = useState("");
  const [parentId, setParentId] = useState("");
  const [areaId, setAreaId] = useState("");
  const [taskIds, setTaskIds] = useState("");
  const [metricTaskId, setMetricTaskId] = useState("");
  const [metricDatasetId, setMetricDatasetId] = useState("");
  const [metricDirection, setMetricDirection] = useState("higher_is_better");
  const [imageError, setImageError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { toast } = useToast();

  const label = kind;
  const supportsImage = kind === "task" || kind === "method";

  useEffect(() => {
    if (!open) {
      setName("");
      setDescription("");
      setYear("");
      setStartDate("");
      setEndDate("");
      setVenue("");
      setUrl("");
      setImage(null);
      setImageSource("");
      setSource("");
      setKeywords("");
      setParentId("");
      setAreaId("");
      setTaskIds("");
      setMetricTaskId("");
      setMetricDatasetId("");
      setMetricDirection("higher_is_better");
      setImageError("");
    }
  }, [open]);

  const selectImage = (file?: File) => {
    if (!file) return;
    setImageError("");
    if (!ACCEPTED_IMAGE_TYPES.includes(file.type)) {
      setImageError("Choose a JPEG, PNG, WebP, or GIF image.");
      return;
    }
    if (file.size > IMAGE_MAX_BYTES) {
      setImageError("Image must be 2 MB or smaller.");
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result !== "string") {
        setImageError("Could not read that image.");
        return;
      }
      setImage({
        file_name: file.name,
        mime_type: file.type,
        data_url: reader.result,
      });
    };
    reader.onerror = () => setImageError("Could not read that image.");
    reader.readAsDataURL(file);
  };

  const handleImageDrop = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault();
    selectImage(event.dataTransfer.files[0]);
  };

  const suggestMutation = useMutation({
    mutationFn: async () => {
      const proposedPayload: Record<string, unknown> = {
        name: name.trim(),
      };
      if (kind === "conference") {
        Object.entries({
          description: description.trim(),
          year: year ? Number(year) : undefined,
          start_date: startDate,
          end_date: endDate,
          venue: venue.trim(),
          url: url.trim(),
        }).forEach(([key, value]) => {
          if (value) proposedPayload[key] = value;
        });
      } else {
        const normalizedDescription = description.trim();
        if (normalizedDescription) {
          proposedPayload.description = normalizedDescription;
        }
        if (supportsImage) {
          if (image) proposedPayload.image = image;
          if (imageSource.trim()) proposedPayload.image_credit = imageSource.trim();
        }
        if (kind === "method" && source.trim()) {
          proposedPayload.source_url = source.trim();
        }
        if (kind === "task") {
          if (keywords.trim()) proposedPayload.keywords = keywords.trim();
          if (parentId) proposedPayload.parent_id = Number(parentId);
          if (areaId) proposedPayload.area_id = Number(areaId);
        }
        if (kind === "benchmark") {
          proposedPayload.task_ids = taskIds
            .split(",")
            .map((value) => Number(value.trim()))
            .filter((value) => Number.isInteger(value) && value > 0);
        }
        if (kind === "metric") {
          proposedPayload.direction = metricDirection;
          proposedPayload.task_id = Number(metricTaskId);
          proposedPayload.dataset_id = Number(metricDatasetId);
        }
      }
      return submitPendingPaperEdit({
        paper_id: paperId ? parseInt(paperId) : null,
        edit_type: KIND_EDIT_TYPE[kind],
        proposed_payload: proposedPayload,
      });
    },
    onSuccess: () => {
      toast({
        title: "Suggestion submitted for review",
        description: `Thanks! An admin will review your suggested ${label} shortly.`,
      });
      onOpenChange(false);
    },
    onError: (err: unknown) => {
      const e = err as { response?: string; message?: string };
      let description = e.message || `Failed to submit your ${label} suggestion.`;
      if (e.response) {
        try {
          const parsed = JSON.parse(e.response);
          if (typeof parsed?.detail === "string") {
            description = parsed.detail;
          } else if (parsed?.detail?.message) {
            description = `${parsed.detail.message} See ${parsed.detail.help || "/rate-limits"} for help.`;
          } else if (Array.isArray(parsed?.detail) && parsed.detail[0]?.msg) {
            description = parsed.detail[0].msg;
          }
        } catch {
          description = e.response;
        }
      }
      toast({
        title: "Could not submit suggestion",
        description,
        variant: "destructive",
      });
    },
  });

  const canSubmit =
    name.trim().length > 0 &&
    (kind === "task" ||
      (kind === "method" && Boolean(source.trim())) ||
      (kind === "conference" && Boolean(year) && Boolean(url.trim())) ||
      (kind === "benchmark" && Boolean(taskIds.trim()) && Boolean(description.trim())) ||
      (kind === "metric" && Boolean(metricTaskId) && Boolean(metricDatasetId) && Boolean(description.trim())));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Suggest a new {label}</DialogTitle>
          <DialogDescription>
            Propose a {label} that isn&apos;t in the list yet. An admin will
            review your suggestion before it&apos;s added.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="suggest-name">Name</Label>
            <Input
              id="suggest-name"
              value={name}
              maxLength={NAME_MAX}
              placeholder={KIND_NAME_PLACEHOLDER[kind]}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="suggest-description">
              Description
              {kind === "task" || kind === "method" || kind === "conference"
                ? " (optional)"
                : ""}
            </Label>
            <Textarea
              id="suggest-description"
              value={description}
              maxLength={DESCRIPTION_MAX}
              placeholder={KIND_DESCRIPTION_PLACEHOLDER[kind]}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          {kind === "task" && (
            <>
              <div className="space-y-2">
                <Label htmlFor="suggest-keywords">Keywords (optional)</Label>
                <Input id="suggest-keywords" value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="comma-separated matching terms" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Input type="number" min="1" value={parentId} onChange={(e) => setParentId(e.target.value)} placeholder="Parent task ID (optional)" />
                <Input type="number" min="1" value={areaId} onChange={(e) => setAreaId(e.target.value)} placeholder="Area ID (optional)" />
              </div>
            </>
          )}
          {kind === "benchmark" && (
            <div className="space-y-2">
              <Label htmlFor="suggest-task-ids">Intended task IDs</Label>
              <Input id="suggest-task-ids" value={taskIds} onChange={(e) => setTaskIds(e.target.value)} placeholder="e.g. 9, 14" />
            </div>
          )}
          {kind === "metric" && (
            <div className="space-y-3">
              <Label>Intended leaderboard</Label>
              <select className="w-full rounded-md border bg-background p-2" value={metricDirection} onChange={(e) => setMetricDirection(e.target.value)}>
                <option value="higher_is_better">Higher is better</option>
                <option value="lower_is_better">Lower is better</option>
              </select>
              <div className="grid grid-cols-2 gap-3">
                <Input type="number" min="1" value={metricTaskId} onChange={(e) => setMetricTaskId(e.target.value)} placeholder="Task ID" />
                <Input type="number" min="1" value={metricDatasetId} onChange={(e) => setMetricDatasetId(e.target.value)} placeholder="Benchmark ID" />
              </div>
            </div>
          )}
          {supportsImage && (
            <>
              <div className="space-y-2">
                <Label>Image (optional)</Label>
                <input
                  ref={fileInputRef}
                  className="sr-only"
                  type="file"
                  accept={ACCEPTED_IMAGE_TYPES.join(",")}
                  onChange={(event) => selectImage(event.target.files?.[0])}
                />
                {image ? (
                  <div className="relative overflow-hidden rounded-md border border-border bg-muted/30">
                    <img
                      src={image.data_url}
                      alt="Selected suggestion"
                      className="max-h-48 w-full object-contain"
                    />
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      className="absolute right-2 top-2 h-8 px-2"
                      onClick={() => {
                        setImage(null);
                        if (fileInputRef.current) fileInputRef.current.value = "";
                      }}
                    >
                      <X className="mr-1 h-4 w-4" />
                      Remove
                    </Button>
                    <div className="truncate border-t border-border px-3 py-2 text-xs text-muted-foreground">
                      {image.file_name}
                    </div>
                  </div>
                ) : (
                  <button
                    type="button"
                    className="flex w-full flex-col items-center justify-center rounded-md border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground transition-colors hover:border-foreground/50 hover:text-foreground"
                    onClick={() => fileInputRef.current?.click()}
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={handleImageDrop}
                  >
                    <ImagePlus className="mb-2 h-6 w-6" />
                    <span>Drop an image here, or click to choose one</span>
                    <span className="mt-1 text-xs">JPEG, PNG, WebP, or GIF · max 2 MB</span>
                  </button>
                )}
                {imageError && (
                  <p className="text-sm text-destructive" role="alert">
                    {imageError}
                  </p>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="suggest-image-source">Image source (optional)</Label>
                <Input
                  id="suggest-image-source"
                  value={imageSource}
                  maxLength={IMAGE_SOURCE_MAX}
                  placeholder="Creator, publication, or source URL"
                  onChange={(event) => setImageSource(event.target.value)}
                />
              </div>
              {kind === "method" && (
                <div className="space-y-2">
                  <Label htmlFor="suggest-method-source">Source URL (optional)</Label>
                  <Input
                    id="suggest-method-source"
                    value={source}
                    maxLength={IMAGE_SOURCE_MAX}
                    placeholder="https://arxiv.org/abs/..."
                    onChange={(event) => setSource(event.target.value)}
                  />
                </div>
              )}
            </>
          )}
          {kind === "conference" && (
            <>
              <div className="space-y-2">
                <Label htmlFor="suggest-year">Edition year</Label>
                <Input
                  id="suggest-year"
                  type="number"
                  min="1900"
                  max="2200"
                  value={year}
                  placeholder="2026"
                  onChange={(e) => setYear(e.target.value)}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div><Label htmlFor="suggest-start-date">Start date (optional)</Label><Input id="suggest-start-date" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} /></div>
                <div><Label htmlFor="suggest-end-date">End date (optional)</Label><Input id="suggest-end-date" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} /></div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="suggest-venue">Venue (optional)</Label>
                <Input
                  id="suggest-venue"
                  value={venue}
                  maxLength={VENUE_MAX}
                  placeholder="e.g. Vancouver Convention Centre, Canada"
                  onChange={(e) => setVenue(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="suggest-url">URL (optional)</Label>
                <Input
                  id="suggest-url"
                  type="url"
                  inputMode="url"
                  value={url}
                  maxLength={URL_MAX}
                  placeholder="https://example.org/conference"
                  onChange={(e) => setUrl(e.target.value)}
                />
              </div>
            </>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => suggestMutation.mutate()}
            disabled={suggestMutation.isPending || !canSubmit}
          >
            {suggestMutation.isPending ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Submitting...
              </>
            ) : (
              <>
                <Check className="w-4 h-4 mr-2" />
                Submit suggestion
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default SuggestTaxonomyDialog;
