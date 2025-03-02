import React, { useEffect, useState, useMemo } from 'react';
import ReactDOM from 'react-dom';
import { createEditor } from 'slate';
import { Slate, Editable, withReact } from 'slate-react';
import { withHistory } from 'slate-history';

// Initialize the editor with history
const SlateEditor = () => {
  const [editor] = useState(() => withHistory(withReact(createEditor())));
  const initialValue = useMemo(() => {
    try {
      const contentField = document.getElementById('document-content');
      return contentField && contentField.value ? JSON.parse(contentField.value) : [{ type: 'paragraph', children: [{ text: '' }] }];
    } catch (error) {
      console.error('Error parsing document content:', error);
      return [{ type: 'paragraph', children: [{ text: '' }] }];
    }
  }, []);

  const [value, setValue] = useState(initialValue);
  const canEdit = document.getElementById('can-edit')?.value === 'True';

  useEffect(() => {
    console.log("Slate.js Editor Mounted!");
  }, []);

  return (
    <Slate editor={editor} value={value} onChange={setValue}>
      <Editable placeholder="Start typing here..." readOnly={!canEdit} className="slate-editor" />
    </Slate>
  );
};

// Mount the React editor
document.addEventListener('DOMContentLoaded', () => {
  const editorContainer = document.getElementById('slate-editor');

  if (editorContainer) {
    try {
      ReactDOM.render(<SlateEditor />, editorContainer);
    } catch (error) {
      console.error("Error rendering Slate editor:", error);
      editorContainer.innerHTML = '<p class="text-danger">Failed to load editor.</p>';
    }
  }
});
