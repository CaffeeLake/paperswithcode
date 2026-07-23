import React from "react";

export interface ModelPickerOption {
  id: string;
  label: string;
}

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
  const widthInCharacters = Math.min(Math.max(selectedLabel.length + 5, 12), 32);

  return (
    <select
      className="chat-model-select"
      style={{ width: `${widthInCharacters}ch` }}
      value={selectedModel}
      disabled={disabled}
      onChange={(event) => onModelChange(event.target.value)}
      aria-label="Research model"
    >
      {!models.some((model) => model.id === selectedModel) && (
        <option value={selectedModel} disabled>{selectedLabel}</option>
      )}
      {models.map((model) => (
        <option key={model.id} value={model.id}>{model.label}</option>
      ))}
    </select>
  );
};

export default ModelPicker;
