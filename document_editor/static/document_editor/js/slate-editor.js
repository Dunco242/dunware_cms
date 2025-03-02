import React, { useCallback, useEffect, useMemo, useState } from 'react';
import ReactDOM from 'react-dom';
import { createEditor, Editor, Transforms, Text, Element as SlateElement } from 'slate';
import { Slate, Editable, withReact, useSlate } from 'slate-react';
import { withHistory } from 'slate-history';
import isHotkey from 'is-hotkey';

const HOTKEYS = {
  'mod+b': 'bold',
  'mod+i': 'italic',
  'mod+u': 'underline',
  'mod+`': 'code',
};

const LIST_TYPES = ['numbered-list', 'bulleted-list'];
const TEXT_ALIGN_TYPES = ['left', 'center', 'right', 'justify'];

const SlateEditor = () => {
  const initialValue = useMemo(() => {
    const contentField = document.getElementById('document-content');

    if (contentField && contentField.value) {
      try {
        const parsedContent = JSON.parse(contentField.value);
        const content = parsedContent.children || parsedContent;

        if (!Array.isArray(content) || content.length === 0) {
          return [{ type: 'paragraph', children: [{ text: '' }] }];
        }

        return content;
      } catch (error) {
        console.error('Error parsing document content:', error);
        return [{ type: 'paragraph', children: [{ text: '' }] }];
      }
    }

    return [{ type: 'paragraph', children: [{ text: '' }] }];
  }, []);

  const [editor] = useState(() => withHistory(withReact(createEditor())));
  const [value, setValue] = useState(initialValue);
  const [isSaving, setIsSaving] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  const documentId = document.getElementById('document-id').value;
  const canEdit = document.getElementById('can-edit').value === 'True';
  const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

  const renderElement = useCallback(props => <Element {...props} />, []);
  const renderLeaf = useCallback(props => <Leaf {...props} />, []);

  const saveDocument = async (createVersion = false) => {
    if (!hasUnsavedChanges && !createVersion) return;

    setIsSaving(true);

    try {
      const response = await fetch(`/documents/${documentId}/save/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify({
          content: { children: value },
          create_version: createVersion,
        }),
      });

      const data = await response.json();

      if (data.success) {
        setHasUnsavedChanges(false);
        showNotification(createVersion ? `Created new version ${data.version}` : 'Document saved successfully', 'success');

        if (data.updated_at) {
          const lastSavedTimeElement = document.getElementById('last-saved-time');
          if (lastSavedTimeElement) {
            lastSavedTimeElement.innerText = new Date(data.updated_at).toLocaleString();
          }
        }
      } else {
        console.error('Error saving document:', data.error);
        showNotification('Error saving document: ' + data.error, 'error');
      }
    } catch (error) {
      console.error('Error saving document:', error);
      showNotification('Error saving document', 'error');
    } finally {
      setIsSaving(false);
    }
  };

  useEffect(() => {
    if (!canEdit) return;

    const saveInterval = setInterval(() => {
      if (hasUnsavedChanges) {
        saveDocument();
      }
    }, 60000); // Auto-save every 60 seconds instead of 30

    return () => clearInterval(saveInterval);
  }, [hasUnsavedChanges]);

  useEffect(() => {
    const handleBeforeUnload = (e) => {
      if (hasUnsavedChanges) {
        const message = 'You have unsaved changes. Are you sure you want to leave?';
        e.returnValue = message;
        return message;
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [hasUnsavedChanges]);

  const handleKeyDown = event => {
    if ((event.ctrlKey || event.metaKey) && event.key === 's') {
      event.preventDefault();
      saveDocument();
      return;
    }

    for (const hotkey in HOTKEYS) {
      if (isHotkey(hotkey, event)) {
        event.preventDefault();
        toggleMark(editor, HOTKEYS[hotkey]);
        return;
      }
    }
  };

  return (
    <div className="slate-editor-container">
      <div className="slate-toolbar bg-gray-100 p-2 rounded-t-md flex items-center space-x-2 border-b">
        <MarkButton format="bold" icon="format_bold" />
        <MarkButton format="italic" icon="format_italic" />
        <MarkButton format="underline" icon="format_underlined" />
        <MarkButton format="code" icon="code" />
      </div>

      <div className="slate-editor border p-4 min-h-[500px] rounded-b-md bg-white">
        <Slate
          editor={editor}
          value={value}
          onChange={newValue => {
            setValue(newValue);
            setHasUnsavedChanges(JSON.stringify(newValue) !== JSON.stringify(initialValue));
          }}
        >
          <Editable
            renderElement={renderElement}
            renderLeaf={renderLeaf}
            placeholder="Start typing here..."
            autoFocus
            spellCheck
            onKeyDown={handleKeyDown}
            readOnly={!canEdit}
            className={!canEdit ? 'opacity-75 cursor-not-allowed' : ''}
          />
        </Slate>
      </div>

      <div className="slate-statusbar text-sm text-gray-500 mt-2 flex justify-between">
        <div>{hasUnsavedChanges ? <span className="text-amber-600">Unsaved changes</span> : <span>No unsaved changes</span>}</div>
        <div>Last saved: <span id="last-saved-time">Never</span></div>
      </div>
    </div>
  );
};

const showNotification = (message, type = 'info') => {
  const notification = document.createElement('div');
  notification.className = `fixed bottom-4 right-4 p-4 rounded-md shadow-lg ${
    type === 'success' ? 'bg-green-50 text-green-800 border border-green-200' :
    type === 'error' ? 'bg-red-50 text-red-800 border border-red-200' :
    'bg-blue-50 text-blue-800 border border-blue-200'
  }`;

  notification.textContent = message;
  document.body.appendChild(notification);

  setTimeout(() => {
    notification.classList.add('opacity-0', 'transition-opacity', 'duration-500');
    setTimeout(() => document.body.removeChild(notification), 500);
  }, 3000);
};

document.addEventListener('DOMContentLoaded', () => {
  const editorContainer = document.getElementById('slate-editor');
  if (editorContainer) {
    try {
      ReactDOM.render(<SlateEditor />, editorContainer);
    } catch (error) {
      console.error('Error rendering Slate editor:', error);
      editorContainer.innerHTML = `<div class="alert alert-danger">Unable to load document editor. Please refresh the page or contact support.</div>`;
    }
  }
});
