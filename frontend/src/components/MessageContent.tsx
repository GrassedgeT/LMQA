import { useState, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/cjs/styles/prism';
import './MessageContent.css';

interface MessageContentProps {
  content: string;
}

/**
 * 消息内容组件
 * 支持 Markdown 渲染和代码高亮
 */
export default function MessageContent({ content }: MessageContentProps) {
  const [copiedCodeBlock, setCopiedCodeBlock] = useState<string | null>(null);

  const handleCopyCode = useCallback(async (code: string, index: number) => {
    try {
      await navigator.clipboard.writeText(code);
      setCopiedCodeBlock(`${index}`);
      setTimeout(() => setCopiedCodeBlock(null), 2000);
    } catch (err) {
      console.error('复制失败:', err);
      // 降级方案：使用传统的复制方法
      try {
        const textArea = document.createElement('textarea');
        textArea.value = code;
        textArea.style.position = 'fixed';
        textArea.style.opacity = '0';
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
        setCopiedCodeBlock(`${index}`);
        setTimeout(() => setCopiedCodeBlock(null), 2000);
      } catch (fallbackErr) {
        console.error('降级复制方案也失败:', fallbackErr);
      }
    }
  }, []);

  // 使用 ref 来跟踪代码块索引（在渲染时递增）
  let codeBlockIndex = 0;

  return (
    <div className="message-content-wrapper">
      <ReactMarkdown
        components={{
          code({ inline, className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '');
            const language = match ? match[1] : '';
            const codeString = String(children).replace(/\n$/, '');
            const currentIndex = !inline && language ? codeBlockIndex++ : -1;
            
            return !inline && language ? (
              <div className="code-block-wrapper" key={currentIndex}>
                <div className="code-block-header">
                  <span className="code-language">{language}</span>
                  <button
                    className="copy-code-btn"
                    onClick={() => handleCopyCode(codeString, currentIndex)}
                    title="复制代码"
                    aria-label="复制代码到剪贴板"
                  >
                    {copiedCodeBlock === `${currentIndex}` ? '✓ 已复制' : '📋 复制'}
                  </button>
                </div>
                <SyntaxHighlighter
                  style={oneLight}
                  language={language}
                  PreTag="div"
                  customStyle={{
                    margin: 0,
                    borderRadius: '0 0 8px 8px',
                  }}
                  {...props}
                >
                  {codeString}
                </SyntaxHighlighter>
              </div>
            ) : (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

