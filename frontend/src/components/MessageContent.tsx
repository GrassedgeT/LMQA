import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/cjs/styles/prism';
import './MessageContent.css';

interface MessageContentProps {
  content: string;
}

export default function MessageContent({ content }: MessageContentProps) {
  const [copiedCodeBlock, setCopiedCodeBlock] = useState<string | null>(null);

  const handleCopyCode = async (code: string, index: number) => {
    try {
      await navigator.clipboard.writeText(code);
      setCopiedCodeBlock(`${index}`);
      setTimeout(() => setCopiedCodeBlock(null), 2000);
    } catch (err) {
      console.error('复制失败:', err);
    }
  };

  let codeBlockIndex = 0;

  return (
    <div className="message-content-wrapper">
      <ReactMarkdown
        components={{
          code({ node, inline, className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '');
            const language = match ? match[1] : '';
            const codeString = String(children).replace(/\n$/, '');
            const currentIndex = !inline && language ? codeBlockIndex++ : -1;
            
            return !inline && language ? (
              <div className="code-block-wrapper">
                <div className="code-block-header">
                  <span className="code-language">{language}</span>
                  <button
                    className="copy-code-btn"
                    onClick={() => handleCopyCode(codeString, currentIndex)}
                    title="复制代码"
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

