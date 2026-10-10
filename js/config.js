/*
 * Axon deployment configuration.
 * Set this to the public HTTPS URL of the FastAPI nudge service (no trailing
 * slash). Leave it blank to use Axon's local, hospital-guide fallback nudges.
 * This file is intentionally plain JavaScript so collaborators can edit it.
 */
window.AXON_NUDGE_API_BASE_URL = "https://synapse-workflow-companion.onrender.com";
