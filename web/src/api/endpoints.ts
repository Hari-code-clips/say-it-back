import { request, requestBlob } from './client.ts'
import { createApi } from './createApi.ts'

/** The API client every screen uses: the endpoint table of createApi.ts over this app's transport (client.ts). */
export const api = createApi({ request, requestBlob })
