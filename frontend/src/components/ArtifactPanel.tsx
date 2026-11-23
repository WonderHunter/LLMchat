import hljs from 'highlight.js/lib/common'
import { X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { artifactTitle, isPreviewable, lineCount, previewDocument } from '../chat/artifacts'
import { useChat, type Artifact } from '../chat/store'
import { CopyButton } from './CopyButton'

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function Panel({ artifact }: { artifact: Artifact }) {
  const setArtifact = useChat((state) => state.setArtifact)
  const previewable = isPreviewable(artifact.language, artifact.code)
  const [tab, setTab] = useState<'preview' | 'code'>(previewable ? 'preview' : 'code')

  // highlight.js échappe le code : le HTML produit ne contient que ses propres balises <span>.
  const highlighted = useMemo(
    () =>
      hljs.getLanguage(artifact.language)
        ? hljs.highlight(artifact.code, { language: artifact.language }).value
        : escapeHtml(artifact.code),
    [artifact],
  )

  const tabClass = (active: boolean) =>
    `rounded-md px-3 py-1 text-sm ${active ? 'bg-surface font-medium shadow-sm' : 'text-muted hover:text-text'}`

  return (
    <aside
      aria-label="Panneau de contenu"
      className="flex h-full w-[46%] min-w-[22rem] shrink-0 flex-col border-l border-border bg-surface max-lg:fixed max-lg:inset-0 max-lg:z-30 max-lg:w-full"
    >
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border px-4">
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-medium">
            {artifactTitle(artifact.language, artifact.code)}
          </h2>
          <p className="text-xs text-muted">{lineCount(artifact.code)} lignes</p>
        </div>
        {previewable && (
          <div className="flex rounded-lg bg-hover p-0.5" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'preview'}
              className={tabClass(tab === 'preview')}
              onClick={() => setTab('preview')}
            >
              Aperçu
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'code'}
              className={tabClass(tab === 'code')}
              onClick={() => setTab('code')}
            >
              Code
            </button>
          </div>
        )}
        <CopyButton text={artifact.code} label="Copier le contenu" />
        <button
          type="button"
          onClick={() => setArtifact(null)}
          title="Fermer le panneau"
          aria-label="Fermer le panneau"
          className="rounded-md p-1.5 text-muted hover:bg-hover hover:text-text"
        >
          <X className="size-5" />
        </button>
      </header>

      {tab === 'preview' && previewable ? (
        // Sans « allow-same-origin » : le contenu généré tourne dans une origine isolée,
        // sans accès aux cookies, au stockage ni à l'API de l'application.
        <iframe
          title="Aperçu"
          sandbox="allow-scripts"
          referrerPolicy="no-referrer"
          srcDoc={previewDocument(artifact.language, artifact.code)}
          className="w-full flex-1 bg-white"
        />
      ) : (
        <pre className="flex-1 overflow-auto bg-code-bg p-4 font-mono text-[13px] leading-relaxed">
          <code dangerouslySetInnerHTML={{ __html: highlighted }} />
        </pre>
      )}
    </aside>
  )
}

export function ArtifactPanel() {
  const artifact = useChat((state) => state.artifact)
  if (!artifact) return null
  // La clé remet l'onglet par défaut quand on ouvre un autre contenu.
  return <Panel key={`${artifact.language}:${artifact.code.length}`} artifact={artifact} />
}
