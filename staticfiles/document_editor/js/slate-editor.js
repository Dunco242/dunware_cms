import React, { useEffect, useState, useMemo } from 'react';
import ReactDOM from 'react-dom';
import { createEditor } from 'slate';
import { Slate, Editable, withReact } from 'slate-react';
import { withHistory } from 'slate-history';

// Ensure that the editor container exists before mounting
document.addEventListener('DOMContentLoaded', () => {
  const editorContainer = document.getElementById('slate-editor');

  if (!editorContainer) {
    console.error("Error: 'slate-editor' container not found.");
    return;
  }

  try {
    ReactDOM.render(<SlateEditor />, editorContainer);
  } catch (error) {
    console.error("Error rendering Slate editor:", error);
    editorContainer.innerHTML = '<p class="text-danger">Failed to load editor.</p>';
  }
});

// Slate.js Editor Component
const SlateEditor = () => {
  const [editor] = useState(() => withHistory(withReact(createEditor())));

  // Fetch document content from hidden textarea
  const initialValue = useMemo(() => {
    const contentField = document.getElementById('document-content');

    if (!contentField) {
      console.error("Error: 'document-content' textarea not found.");
      return [{ type: 'paragraph', children: [{ text: '' }] }];
    }

    try {
      const content = contentField.value.trim();
      console.log("Loaded document content:", content); // Debugging output

      return content ? JSON.parse(content) : [{ type: 'paragraph', children: [{ text: '' }] }];
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
