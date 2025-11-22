// 工具函数

export const handleError = (err: unknown, defaultMessage: string = '操作失败') => {
  const message = err instanceof Error ? err.message : defaultMessage;
  console.error(message, err);
  alert(message);
};

