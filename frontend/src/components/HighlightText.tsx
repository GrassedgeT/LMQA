import { useMemo } from 'react';

interface HighlightTextProps {
  text: string;
  highlight: string;
}

/**
 * 高亮文本组件
 * 用于在文本中高亮显示指定的关键词
 */
export default function HighlightText({ text, highlight }: HighlightTextProps) {
  const highlightedParts = useMemo(() => {
    if (!highlight || !highlight.trim()) {
      return [{ text, isHighlight: false }];
    }

    // 转义特殊字符，避免正则表达式错误
    const escapedHighlight = highlight.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(${escapedHighlight})`, 'gi');
    const parts = text.split(regex);
    
    return parts.map((part) => ({
      text: part,
      isHighlight: part.toLowerCase() === highlight.toLowerCase(),
    }));
  }, [text, highlight]);
  
  return (
    <span>
      {highlightedParts.map((part, index) => 
        part.isHighlight ? (
          <mark 
            key={index} 
            style={{ 
              backgroundColor: '#fef08a', 
              padding: '0 2px',
              borderRadius: '2px',
            }}
            aria-label={`高亮: ${part.text}`}
          >
            {part.text}
          </mark>
        ) : (
          <span key={index}>{part.text}</span>
        )
      )}
    </span>
  );
}

