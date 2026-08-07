import React from "react";

export interface ModelPickerOption {
  id: string;
  label: string;
  provider?: "huggingface" | "openrouter";
}

const PROVIDER_GROUPS = [
  { provider: "huggingface", label: "Inference Providers" },
  { provider: "openrouter", label: "OpenRouter" },
] as const;

interface ModelPickerProps {
  models: ModelPickerOption[];
  selectedModel: string;
  onModelChange: (model: string) => void;
  disabled?: boolean;
}

const ModelPicker: React.FC<ModelPickerProps> = ({
  models,
  selectedModel,
  onModelChange,
  disabled,
}) => {
  const selectedLabel = models.find((model) => model.id === selectedModel)?.label
    ?? `${selectedModel} (unavailable)`;
  const ungroupedModels = models.filter((model) => !model.provider);

  if (models.length === 1 && models[0]?.id === selectedModel) {
    return <span className="chat-model-label" aria-label="Research model">{selectedLabel}</span>;
  }

  return (
    <span className={`chat-model-picker${disabled ? " is-disabled" : ""}`}>
      <span className="chat-model-picker-sizer" aria-hidden="true">{selectedLabel}</span>
      <select
        className="chat-model-select"
        value={selectedModel}
        disabled={disabled}
        onChange={(event) => onModelChange(event.target.value)}
        aria-label="Research model"
      >
        {!models.some((model) => model.id === selectedModel) && (
          <option value={selectedModel} disabled>{selectedLabel}</option>
        )}
        {ungroupedModels.map((model) => (
          <option key={model.id} value={model.id}>{model.label}</option>
        ))}
        {PROVIDER_GROUPS.map(({ provider, label }) => {
          const providerModels = models.filter((model) => model.provider === provider);
          if (providerModels.length === 0) return null;
          return (
            <optgroup key={provider} label={label}>
              {providerModels.map((model) => (
                <option key={model.id} value={model.id}>{model.label}</option>
              ))}
            </optgroup>
          );
        })}
      </select>
      <svg className="chat-model-picker-chevron" viewBox="0 0 12 8" aria-hidden="true">
        <path d="m1 1 5 5 5-5" />
      </svg>
    </span>
  );
};

export default ModelPicker;
