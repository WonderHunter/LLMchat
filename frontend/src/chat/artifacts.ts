const PREVIEWABLE = new Set(['html', 'svg', 'xml'])
const LONG_BLOCK_LINES = 15

export function lineCount(code: string): number {
  return code.split('\n').length
}

/** Peut être rendu dans l'onglet Aperçu. */
export function isPreviewable(language: string, code: string): boolean {
  if (!PREVIEWABLE.has(language)) return false
  return language !== 'xml' || code.trimStart().startsWith('<svg')
}

/** Mérite un bouton « ouvrir dans le panneau ». */
export function isArtifact(language: string, code: string): boolean {
  return isPreviewable(language, code) || lineCount(code) >= LONG_BLOCK_LINES
}

export function artifactTitle(language: string, code: string): string {
  if (language === 'html') return 'Page HTML'
  if (isPreviewable(language, code)) return 'Image SVG'
  return language === 'texte' ? 'Texte' : `Code ${language}`
}

/** Document chargé dans l'iframe d'aperçu. */
export function previewDocument(language: string, code: string): string {
  if (language === 'html') return code
  return `<!doctype html><body style="margin:0;min-height:100vh;display:grid;place-items:center">${code}</body>`
}
