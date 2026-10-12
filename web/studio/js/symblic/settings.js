// Reads and writes the text mode's default-settings form; normalizeDefaults is pure.
import { normalizeContextMode } from './utils.js';

function readNumberInput(el) {
  if (!el) return undefined;
  const value = el.value.trim();
  if (!value) return undefined;
  const parsed = Number(value);
  return Number.isNaN(parsed) ? undefined : parsed;
}

export function collectSettings(elements) {
  return {
    workflowName: elements.workflowNameEl.value.trim(),
    provider: elements.providerEl.value,
    model: elements.modelEl.value.trim(),
    system: elements.systemEl.value.trim(),
    responseStyle: elements.responseStyleEl.value.trim(),
    contextMode: elements.defaultContextModeEl.value,
    contextKey: elements.contextKeyEl.value.trim(),
    contextScope: elements.contextScopeEl.value,
    outputMode: elements.outputModeEl.value,
    maxMessages: readNumberInput(elements.maxMessagesEl),
    maxChars: readNumberInput(elements.maxCharsEl),
    maxTokens: readNumberInput(elements.maxTokensEl),
    contextWindow: readNumberInput(elements.contextWindowEl),
    temperature: readNumberInput(elements.temperatureEl),
    fileInputs: elements.fileInputsEl.value.trim(),
    fileMaxChars: readNumberInput(elements.fileMaxCharsEl)
  };
}

export function applySettings(elements, settings) {
  if (!settings) return;
  if (settings.workflowName) elements.workflowNameEl.value = settings.workflowName;
  if (settings.provider) elements.providerEl.value = settings.provider;
  if (settings.model) elements.modelEl.value = settings.model;
  if (settings.system) elements.systemEl.value = settings.system;
  if (settings.responseStyle) elements.responseStyleEl.value = settings.responseStyle;
  if (settings.contextMode) elements.defaultContextModeEl.value = settings.contextMode;
  if (settings.contextKey) elements.contextKeyEl.value = settings.contextKey;
  if (settings.contextScope) elements.contextScopeEl.value = settings.contextScope;
  if (settings.outputMode) elements.outputModeEl.value = settings.outputMode;
  if (settings.maxMessages != null) elements.maxMessagesEl.value = settings.maxMessages;
  if (settings.maxChars != null) elements.maxCharsEl.value = settings.maxChars;
  if (settings.maxTokens != null) elements.maxTokensEl.value = settings.maxTokens;
  if (settings.contextWindow != null) elements.contextWindowEl.value = settings.contextWindow;
  if (settings.temperature != null) elements.temperatureEl.value = settings.temperature;
  if (settings.fileInputs) elements.fileInputsEl.value = settings.fileInputs;
  if (settings.fileMaxChars != null) elements.fileMaxCharsEl.value = settings.fileMaxChars;
}

export function normalizeDefaults(settings) {
  return {
    provider: settings.provider || 'ollama',
    model: settings.model || 'llama3.1',
    system: settings.system || '',
    responseStyle: settings.responseStyle || '',
    contextMode: normalizeContextMode(settings.contextMode || 'clear'),
    contextKey: settings.contextKey || 'symblic',
    contextScope: settings.contextScope || 'workflow',
    outputMode: settings.outputMode || 'app',
    maxMessages: settings.maxMessages,
    maxChars: settings.maxChars,
    maxTokens: settings.maxTokens,
    contextWindow: settings.contextWindow,
    temperature: settings.temperature,
    fileInputs: settings.fileInputs || '',
    fileMaxChars: settings.fileMaxChars
  };
}
