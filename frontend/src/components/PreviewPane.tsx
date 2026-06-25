import BrowserPreview from './BrowserPreview'

const DEFAULT_MAKER_URL = 'https://maker.taptap.cn/'

interface PreviewPaneProps {
  activePath: string
  content: string
  onCollapse?: () => void
}

export default function PreviewPane({ onCollapse }: PreviewPaneProps) {
  return (
    <div className="preview-pane maker-browser-pane">
      <div className="preview-content">
        <BrowserPreview initialUrl={DEFAULT_MAKER_URL} />
      </div>
      {onCollapse && (
        <button className="preview-collapse-button" onClick={onCollapse} title="收起预览面板">
          ›
        </button>
      )}
    </div>
  )
}
