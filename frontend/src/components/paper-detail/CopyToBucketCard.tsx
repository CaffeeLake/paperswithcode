import React, { useMemo, useState } from "react";

import { Icon } from "@/components";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { useToast } from "@/hooks/use-toast";

export type BucketArtifactKind = "model" | "dataset" | "space" | "github";

export interface BucketArtifact {
  id: string;
  kind: BucketArtifactKind;
  label: string;
  url: string;
  source: string;
  destination: string;
}

interface CopyToBucketCardProps {
  githubUrls: string[];
  hfModelUrls: string[];
  hfDatasetUrls: string[];
  hfSpaceUrls: string[];
  suggestedBucketId?: string;
}

const KIND_LABEL: Record<BucketArtifactKind, string> = {
  model: "Model",
  dataset: "Dataset",
  space: "Space",
  github: "GitHub",
};
const REPO_PART_RE = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

function shellQuote(value: string): string {
  return "'" + value.replace(/'/g, "'\"'\"'") + "'";
}

function parseHfArtifact(
  url: string,
  kind: Exclude<BucketArtifactKind, "github">,
): BucketArtifact | null {
  try {
    const parsed = new URL(url);
    if (parsed.hostname !== "huggingface.co") return null;

    const parts = parsed.pathname.split("/").filter(Boolean);
    const prefix = kind === "model" ? [] : [`${kind}s`];
    if (prefix.length && parts[0] !== prefix[0]) return null;
    const repoParts = parts.slice(prefix.length, prefix.length + 2);
    if (repoParts.length !== 2 || repoParts.some((part) => !REPO_PART_RE.test(part))) return null;

    const repoId = repoParts.join("/");
    const sourcePrefix = kind === "model" ? "" : `${kind}s/`;
    return {
      id: `${kind}:${repoId}`,
      kind,
      label: repoId,
      url: `https://huggingface.co/${sourcePrefix}${repoId}`,
      source: `hf://${sourcePrefix}${repoId}/`,
      destination: `${kind}s/${repoId}/`,
    };
  } catch {
    return null;
  }
}

function parseGithubArtifact(url: string): BucketArtifact | null {
  try {
    const parsed = new URL(url);
    if (parsed.hostname !== "github.com" && parsed.hostname !== "www.github.com") return null;
    const parts = parsed.pathname.split("/").filter(Boolean);
    if (parts.length < 2) return null;

    const owner = parts[0];
    const repo = parts[1].replace(/\.git$/, "");
    if (!REPO_PART_RE.test(owner) || !REPO_PART_RE.test(repo)) return null;
    const repoId = `${owner}/${repo}`;
    return {
      id: `github:${repoId}`,
      kind: "github",
      label: repoId,
      url: `https://github.com/${repoId}`,
      source: `https://github.com/${repoId}.git`,
      destination: `github/${repoId}/`,
    };
  } catch {
    return null;
  }
}

export function collectBucketArtifacts({
  githubUrls,
  hfModelUrls,
  hfDatasetUrls,
  hfSpaceUrls,
}: CopyToBucketCardProps): BucketArtifact[] {
  const candidates = [
    ...hfModelUrls.map((url) => parseHfArtifact(url, "model")),
    ...hfDatasetUrls.map((url) => parseHfArtifact(url, "dataset")),
    ...hfSpaceUrls.map((url) => parseHfArtifact(url, "space")),
    ...githubUrls.map(parseGithubArtifact),
  ];
  const seen = new Set<string>();
  return candidates.filter((artifact): artifact is BucketArtifact => {
    if (!artifact || seen.has(artifact.id)) return false;
    seen.add(artifact.id);
    return true;
  });
}

export function buildBucketCopyCommands(
  bucketId: string,
  artifacts: BucketArtifact[],
  options: { create: boolean; isPrivate: boolean },
): string {
  const lines = [
    "# Requires the Hugging Face CLI: https://huggingface.co/docs/huggingface_hub/guides/cli",
    `HF_BUCKET=${shellQuote(bucketId.trim())}`,
  ];

  if (options.create) {
    lines.push(
      `hf buckets create "$HF_BUCKET" --exist-ok${options.isPrivate ? " --private" : ""}`,
    );
  }

  for (const artifact of artifacts.filter((item) => item.kind !== "github")) {
    lines.push(
      `hf cp ${shellQuote(artifact.source)} "hf://buckets/$HF_BUCKET/${artifact.destination}"`,
    );
  }

  const githubArtifacts = artifacts.filter((item) => item.kind === "github");
  if (githubArtifacts.length) {
    lines.push(
      'PWC_COPY_DIR="$(mktemp -d)"',
      "trap 'rm -rf \"$PWC_COPY_DIR\"' EXIT",
    );
    for (const artifact of githubArtifacts) {
      const localPath = `$PWC_COPY_DIR/${artifact.destination.replace(/\/$/, "")}`;
      lines.push(
        `git clone --depth 1 -- ${shellQuote(artifact.source)} "${localPath}"`,
        `hf sync "${localPath}" "hf://buckets/$HF_BUCKET/${artifact.destination}" --exclude '.git/**'`,
      );
    }
  }

  return lines.join("\n");
}

export function paperArtifactBucketName(title: string): string {
  const shortTitle = title.split(/[:|–—]/, 1)[0] || title;
  const slug = shortTitle
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48)
    .replace(/-+$/g, "");
  return `${slug || "paper"}-artifacts`;
}

export function CopyToBucketCard(props: CopyToBucketCardProps) {
  const { toast } = useToast();
  const artifacts = useMemo(
    () => collectBucketArtifacts(props),
    [props.githubUrls, props.hfDatasetUrls, props.hfModelUrls, props.hfSpaceUrls],
  );
  const [open, setOpen] = useState(false);
  const [destinationMode, setDestinationMode] = useState<"new" | "existing">("new");
  const [bucketId, setBucketId] = useState("");
  const [visibility, setVisibility] = useState<"public" | "private">("public");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    () => new Set(artifacts.map((artifact) => artifact.id)),
  );

  const selectedArtifacts = artifacts.filter((artifact) => selectedIds.has(artifact.id));
  const bucketIdIsValid = /^[A-Za-z0-9][\w.-]*\/[A-Za-z0-9][\w.-]*$/.test(bucketId.trim());
  const commands = buildBucketCopyCommands(bucketId, selectedArtifacts, {
    create: destinationMode === "new",
    isPrivate: visibility === "private",
  });

  const toggleArtifact = (id: string, checked: boolean) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const copyCommands = async () => {
    try {
      await navigator.clipboard.writeText(commands);
      toast({
        title: "Bucket copy commands copied",
        description: "Run them in a terminal where the Hugging Face CLI is signed in.",
      });
    } catch {
      toast({
        title: "Copy failed",
        description: "Could not access the clipboard. Select and copy the commands manually.",
        variant: "destructive",
      });
    }
  };

  const openDialog = () => {
    setSelectedIds(new Set(artifacts.map((artifact) => artifact.id)));
    if (!bucketId && props.suggestedBucketId) {
      setBucketId(props.suggestedBucketId);
    }
    setOpen(true);
  };

  return (
    <>
      <div className="sidebar-card copy-to-bucket-card">
        <button
          type="button"
          className="copy-to-bucket-trigger"
          onClick={openDialog}
        >
          <span className="copy-to-bucket-arrow" aria-hidden="true">→</span>
          <span>Copy to bucket</span>
          <span className="copy-to-bucket-new">New</span>
        </button>
        <div className="copy-to-bucket-meta">
          {artifacts.length
            ? `${artifacts.length} linked artifact${artifacts.length === 1 ? "" : "s"}`
            : "No linked artifacts yet"}
        </div>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <span className="copy-to-bucket-dialog-arrow" aria-hidden="true">→</span>
              Copy to bucket
            </DialogTitle>
            <DialogDescription>
              Keep your own copy of this paper&apos;s linked code and Hugging Face
              artifacts. Hub repositories use Xet&apos;s server-side copy; GitHub
              repositories are cloned into the same destination.
            </DialogDescription>
          </DialogHeader>

          {artifacts.length ? (
            <div className="space-y-5">
              <div className="space-y-2">
                <Label>Choose your destination</Label>
                <RadioGroup
                  value={destinationMode}
                  onValueChange={(value) => setDestinationMode(value as "new" | "existing")}
                  className="grid grid-cols-2 gap-2"
                >
                  <Label className="bucket-choice">
                    <RadioGroupItem value="new" />
                    New bucket
                  </Label>
                  <Label className="bucket-choice">
                    <RadioGroupItem value="existing" />
                    Existing bucket
                  </Label>
                </RadioGroup>
              </div>

              <div className="space-y-2">
                <Label htmlFor="bucket-id">Bucket name</Label>
                <Input
                  id="bucket-id"
                  value={bucketId}
                  onChange={(event) => setBucketId(event.target.value)}
                  placeholder={props.suggestedBucketId || "username/paper-artifacts"}
                  aria-invalid={bucketId.length > 0 && !bucketIdIsValid}
                />
                <p className="text-xs text-muted-foreground">
                  Use the full Hugging Face bucket ID: namespace/name.
                </p>
              </div>

              {destinationMode === "new" && (
                <div className="space-y-2">
                  <Label>Bucket visibility</Label>
                  <RadioGroup
                    value={visibility}
                    onValueChange={(value) => setVisibility(value as "public" | "private")}
                    className="flex gap-5"
                  >
                    <Label className="flex items-center gap-2 font-normal">
                      <RadioGroupItem value="public" />
                      Public
                    </Label>
                    <Label className="flex items-center gap-2 font-normal">
                      <RadioGroupItem value="private" />
                      Private
                    </Label>
                  </RadioGroup>
                </div>
              )}

              <div className="space-y-2">
                <Label>Artifacts</Label>
                <div className="bucket-artifact-list">
                  {artifacts.map((artifact) => (
                    <div key={artifact.id} className="bucket-artifact-row">
                      <Checkbox
                        id={`bucket-artifact-${artifact.id}`}
                        checked={selectedIds.has(artifact.id)}
                        onCheckedChange={(checked) => toggleArtifact(artifact.id, checked === true)}
                      />
                      <Label
                        htmlFor={`bucket-artifact-${artifact.id}`}
                        className="min-w-0 flex-1 cursor-pointer font-normal"
                      >
                        <span className="bucket-artifact-kind">{KIND_LABEL[artifact.kind]}</span>
                        <span className="bucket-artifact-name">{artifact.label}</span>
                      </Label>
                      <a
                        href={artifact.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="bucket-artifact-open"
                      >
                        {artifact.kind === "github" ? "Open" : "Web copy"}
                        <Icon name="external" size={10} />
                      </a>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">
                  “Web copy” opens the artifact&apos;s native Hugging Face page,
                  where its Copy to bucket button is also available.
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="bucket-copy-commands">Copy workflow</Label>
                <pre id="bucket-copy-commands" className="bucket-copy-commands">
                  {bucketIdIsValid
                    ? commands
                    : "Enter a bucket name above to prepare the copy commands."}
                </pre>
              </div>
            </div>
          ) : (
            <p className="py-5 text-sm text-muted-foreground">
              This paper does not have a linked GitHub repository or Hugging Face
              artifact to copy yet.
            </p>
          )}

          <DialogFooter>
            <a
              href="https://huggingface.co/docs/huggingface_hub/en/guides/buckets"
              target="_blank"
              rel="noopener noreferrer"
              className="mr-auto text-sm text-muted-foreground underline underline-offset-4"
            >
              About Hugging Face Buckets
            </a>
            <Button
              type="button"
              onClick={copyCommands}
              disabled={!bucketIdIsValid || selectedArtifacts.length === 0}
            >
              <Icon name="copy" size={12} />
              Copy commands
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
