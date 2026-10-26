document.querySelectorAll('[data-copy]').forEach(button => {
  button.addEventListener('click', async () => {
    const field = document.getElementById(button.dataset.copy);
    const status = document.getElementById('copy_status');
    try {
      await navigator.clipboard.writeText(field.value);
      status.textContent = button.dataset.copySuccess || 'Copied. Paste the prompt into your ChatGPT session.';
    } catch {
      field.focus();
      field.select();
      status.textContent = 'Prompt selected. Use your browser’s Copy command.';
    }
  });
});
