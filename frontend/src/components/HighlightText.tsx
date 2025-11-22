interface HighlightTextProps {
  text: string;
  highlight: string;
}

export default function HighlightText({ text, highlight }: HighlightTextProps) {
  if (!highlight || !highlight.trim()) {
    return <span>{text}</span>;
  }

  const parts = text.split(new RegExp(`(${highlight.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'));
  
  return (
    <span>
      {parts.map((part, index) => {
        const isHighlight = part.toLowerCase() === highlight.toLowerCase();
        return isHighlight ? (
          <mark key={index} style={{ backgroundColor: '#fef08a', padding: '0 2px' }}>
            {part}
          </mark>
        ) : (
          <span key={index}>{part}</span>
        );
      })}
    </span>
  );
}

