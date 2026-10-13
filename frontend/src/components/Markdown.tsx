import { FileCode2, PanelRightOpen } from 'lucide-react'
import { isValidElement, memo, type ComponentProps, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import remarkGfm from 'remark-gfm'
import { artifactTitle, isArtifact, isPreviewable, lineCount } from '../chat/artifacts'
import { useChat } from '../chat/store'
import { CopyButton } from './CopyButton'

function textOf(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textOf).join('')
  if (isValidElement<{ children?: ReactNode }>(node)) return textOf(node.props.children)
  return ''
}

function CodeBlock({ children }: ComponentProps<'pre'>) {
  const setArtifact = useChat((state) => state.setArtifact)
  const className = isValidElement<{ className?: string }>(children)
    ? (children.props.className ?? '')
    : ''
  const language = /language-([\w+#-]+)/.exec(className)?.[1] ?? 'texte'
  const source = textOf(children).replace(/\n$/, '')
  const open = () => setArtifact({ language, code: source })

  // Ce qui peut s'afficher (page HTML, image SVG) devient une carte qui ouvre le panneau.
  if (isPreviewable(language, source)) {
    return (
      <button
        type="button"
        onClick={open}
        className="not-prose my-4 flex w-full max-w-md items-center gap-3 rounded-2xl border border-border bg-surface p-3 text-left shadow-sm transition-colors hover:border-accent"
      >
        <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent">
          <FileCode2 className="size-5" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">
            {artifactTitle(language, source)}
          </span>
          <span className="block text-xs text-muted">
            {lineCount(source)} lignes · cliquer pour ouvrir l'aperçu
          </span>
        </span>
        <PanelRightOpen className="size-4 shrink-0 text-muted" />
      </button>
    )
  }

  return (
    <div className="not-prose my-4 overflow-hidden rounded-xl border border-border bg-code-bg">
      <div className="flex items-center gap-1 border-b border-border py-1 pr-2 pl-4 text-xs text-muted">
        <span className="flex-1">{language}</span>
        {isArtifact(language, source) && (
          <button
            type="button"
            onClick={open}
            title="Ouvrir dans le panneau"
            aria-label="Ouvrir dans le panneau"
            className="rounded-md p-1.5 transition-colors hover:bg-hover hover:text-text"
          >
            <PanelRightOpen className="size-4" />
          </button>
        )}
        <CopyButton text={source} label="Copier le code" />
      </div>
      <pre className="overflow-x-auto p-4 font-mono text-[13px] leading-relaxed">{children}</pre>
    </div>
  )
}

const remarkPlugins = [remarkGfm]
const rehypePlugins = [rehypeHighlight]
const components = {
  pre: CodeBlock,
  a: (props: ComponentProps<'a'>) => <a {...props} target="_blank" rel="noreferrer noopener" />,
}

export const Markdown = memo(function Markdown({ text }: { text: string }) {
  return (
    <div className="prose max-w-none break-words">
      <ReactMarkdown
        remarkPlugins={remarkPlugins}
        rehypePlugins={rehypePlugins}
        components={components}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
})
