import { InMemoryCredentialStore } from "@earendil-works/pi-ai";
import { ModelRuntime } from "@earendil-works/pi-coding-agent";

export const PROVIDER_ID = "pwc-gateway";
export const PLACEHOLDER_KEY = "sandbox-placeholder-not-a-credential";

export async function createProvider(modelId: string) {
  const credentials = new InMemoryCredentialStore();
  const runtime = await ModelRuntime.create({
    credentials,
    modelsPath: null,
    allowModelNetwork: false,
    refreshOnCreate: false,
  });
  runtime.registerProvider(PROVIDER_ID, {
    name: "PwC Gateway",
    baseUrl: "http://127.0.0.1:8765",
    apiKey: PLACEHOLDER_KEY,
    api: "anthropic-messages",
    authHeader: true,
    models: [
      {
        id: modelId,
        name: modelId,
        api: "anthropic-messages",
        baseUrl: "http://127.0.0.1:8765",
        reasoning: true,
        thinkingLevelMap: {
          off: null,
          low: "low",
          medium: "high",
          high: "high",
          xhigh: "max",
          max: "max",
        },
        input: ["text"],
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        contextWindow: 200000,
        maxTokens: 8000,
        compat: {
          supportsEagerToolInputStreaming: true,
          supportsCacheControlOnTools: true,
          supportsTemperature: false,
        },
      },
    ],
  });
  const model = runtime.getModel(PROVIDER_ID, modelId);
  if (!model) throw new Error("PwC Pi model registration failed");
  return { runtime, model };
}

export function thinkingLevel(effort: string): "low" | "high" | "max" {
  if (effort === "low") return "low";
  if (effort === "max") return "max";
  return "high";
}
