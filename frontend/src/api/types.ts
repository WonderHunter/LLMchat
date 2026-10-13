export interface User {
  id: number
  email: string
}

export interface KeyStatus {
  provider: string
  label: string
  keys_url: string
  has_key: boolean
  last4: string | null
  /** null pour les fournisseurs où le réglage n'existe pas. */
  free_only: boolean | null
}

export interface ModelInfo {
  id: string
  name: string
  free: boolean
  /** Le modèle sait-il lire les images jointes ? */
  accepts_images: boolean
  context_length: number | null
  /** Dollars par million de tokens. */
  input_price: number | null
  output_price: number | null
}

export interface ProviderModels {
  provider: string
  label: string
  models: ModelInfo[]
  error: string | null
}

export interface Conversation {
  id: string
  title: string
  provider: string
  model: string
  created_at: string
  updated_at: string
}

export interface Attachment {
  id: string
  /** « image » : envoyée telle quelle au modèle ; « text » : document dont le texte est inséré. */
  kind: 'image' | 'text'
  filename: string
  media_type: string
  size: number
}

export interface Message {
  id: number
  role: 'user' | 'assistant'
  content: string
  provider: string | null
  model: string | null
  /** Consommation des réponses ; null si le fournisseur ne l'a pas communiquée. */
  input_tokens: number | null
  output_tokens: number | null
  /** En dollars ; null quand aucun prix n'est connu pour ce modèle. */
  cost: number | null
  created_at: string
  attachments: Attachment[]
}

export interface ConversationDetail extends Conversation {
  messages: Message[]
}

export interface Selection {
  provider: string
  model: string
}
