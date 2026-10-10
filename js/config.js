/*
 * Axon deployment configuration.
 * Set this to the public HTTPS URL of the FastAPI nudge service (no trailing
 * slash). Leave it blank to use Axon's local, hospital-guide fallback nudges.
 * This file is intentionally plain JavaScript so collaborators can edit it.
 */
window.AXON_NUDGE_API_BASE_URL = "https://synapse-workflow-companion.onrender.com";

// Public Worker endpoint only. The OpenAI key stays in Cloudflare as
// OPENAI_API_KEY and must never be placed in this file.
window.AXON_CHAT_API_BASE_URL = "https://axon-chatbot.george-asrian.workers.dev";
