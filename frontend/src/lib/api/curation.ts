import { PaperCurationCoordinator } from "../paperCuration";
import { apiRequest } from "./request";

export const paperCuration = new PaperCurationCoordinator(apiRequest);
