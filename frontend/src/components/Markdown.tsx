import { isValidElement, memo, type ComponentProps, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import remarkGfm from 'remark-gfm'
import { CopyButton } from './CopyButton'

function textOf(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textOf).join('')
  if (isValidElement<{ children?: ReactNode }>(node)) return textOf(node.props.children)
  return ''
}

function CodeBlock({ children }: ComponentProps<'pre'>) {
  const className = isValidElement<{ className?: string }>(children)
    ? (children.props.className ?? '')
    : ''
  const language = /language-([\w+#-]+)/.exec(className)?.[1] ?? 'texte'
  const source = textOf(children).replace(/\n$/, '')

  return (
    <div className="not-prose my-4 overflow-hidden rounded-xl border border-border bg-code-bg">
      <div className="flex items-center justify-between border-b border-border py-1 pr-2 pl-4 text-xs text-muted">
        <span>{language}</span>
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
