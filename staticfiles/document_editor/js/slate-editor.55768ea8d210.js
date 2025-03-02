// Import required Slate.js libraries
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import ReactDOM from 'react-dom';
import { createEditor, Editor, Transforms, Text, Element as SlateElement } from 'slate';
import { Slate, Editable, withReact, useSlate } from 'slate-react';
import { withHistory } from 'slate-history';
import isHotkey from 'is-hotkey';

// Define hotkeys for basic formatting
const HOTKEYS = {
  'mod+b': 'bold',
  'mod+i': 'italic',
  'mod+u': 'underline',
  'mod+`': 'code',
};

// Define block types for the toolbar
const LIST_TYPES = ['numbered-list', 'bulleted-list'];
const TEXT_ALIGN_TYPES = ['left', 'center', 'right', 'justify'];

// Initialize the Slate editor component
const SlateEditor = () => {
  // Get initial value from the document content field
  const initialValue = useMemo(() => {
    const contentField = document.getElementById('document-content');
    if (contentField && contentField.value) {
      try {
        return JSON.parse(contentField.value);
      } catch (error) {
        console.error('Error parsing document content:', error);
      }
    }

    // Default empty document structure
    return [
      {
        type: 'paragraph',
        children: [{ text: '' }],
      },
    ];
  }, []);

  // Create the editor instance
  const [editor] = useState(() => withHistory(withReact(createEditor())));

  // State for tracking whether the document has unsaved changes
  const [value, setValue] = useState(initialValue);
  const [isSaving, setIsSaving] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  // Get document info
  const documentId = document.getElementById('document-id').value;
  const canEdit = document.getElementById('can-edit').value === 'True';
  const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

  // Function to render elements (paragraphs, headings, etc.)
  const renderElement = useCallback(props => <Element {...props} />, []);

  // Function to render leaf elements (bold, italic, etc.)
  const renderLeaf = useCallback(props => <Leaf {...props} />, []);

  // Save the document content
  const saveDocument = async (createVersion = false) => {
    if (!hasUnsavedChanges && !createVersion) return;

    setIsSaving(true);

    try {
      const response = await fetch(`/documents/${documentId}/save-content/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify({
          content: value,
          create_version: createVersion,
        }),
      });

      const data = await response.json();

      if (data.success) {
        setHasUnsavedChanges(false);

        // Show success message
        const successMsg = createVersion
          ? `Created new version ${data.version}`
          : 'Document saved successfully';

        // Display a toast notification
        showNotification(successMsg, 'success');

        // Update the last saved time
        if (data.updated_at) {
          document.getElementById('last-saved-time').innerText =
            new Date(data.updated_at).toLocaleString();
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

  // Auto-save the document every 30 seconds if there are unsaved changes
  useEffect(() => {
    if (!canEdit) return;

    const interval = setInterval(() => {
      if (hasUnsavedChanges) {
        saveDocument();
      }
    }, 30000);

    return () => clearInterval(interval);
  }, [hasUnsavedChanges]);

  // Set up autosave on page unload
  useEffect(() => {
    const handleBeforeUnload = (e) => {
      if (hasUnsavedChanges) {
        const message = 'You have unsaved changes. Are you sure you want to leave?';
        e.returnValue = message;
        return message;
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, [hasUnsavedChanges]);

  // Handle keyboard shortcuts
  const handleKeyDown = event => {
    // Save document on Ctrl+S
    if ((event.ctrlKey || event.metaKey) && event.key === 's') {
      event.preventDefault();
      saveDocument();
      return;
    }

    // Apply formatting on hotkeys
    for (const hotkey in HOTKEYS) {
      if (isHotkey(hotkey, event)) {
        event.preventDefault();
        const mark = HOTKEYS[hotkey];
        toggleMark(editor, mark);
        return;
      }
    }
  };

  return (
    <div className="slate-editor-container">
      {/* Toolbar */}
      <div className="slate-toolbar bg-gray-100 p-2 rounded-t-md flex items-center space-x-2 border-b">
        <MarkButton format="bold" icon="format_bold" />
        <MarkButton format="italic" icon="format_italic" />
        <MarkButton format="underline" icon="format_underlined" />
        <MarkButton format="code" icon="code" />
        <div className="border-r border-gray-300 h-6 mx-1"></div>
        <BlockButton format="heading-one" icon="looks_one" />
        <BlockButton format="heading-two" icon="looks_two" />
        <BlockButton format="block-quote" icon="format_quote" />
        <BlockButton format="numbered-list" icon="format_list_numbered" />
        <BlockButton format="bulleted-list" icon="format_list_bulleted" />
        <div className="border-r border-gray-300 h-6 mx-1"></div>
        <div className="flex-grow"></div>
        <button
          disabled={isSaving || !hasUnsavedChanges}
          onClick={() => saveDocument()}
          className={`inline-flex items-center px-3 py-1 border border-transparent text-sm font-medium rounded-md shadow-sm text-white ${
            isSaving || !hasUnsavedChanges
              ? 'bg-gray-400 cursor-not-allowed'
              : 'bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500'
          }`}
        >
          {isSaving ? 'Saving...' : 'Save'}
        </button>
        <button
          onClick={() => saveDocument(true)}
          className="inline-flex items-center px-3 py-1 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
        >
          Save as New Version
        </button>
      </div>

      {/* Editor */}
      <div className="slate-editor border p-4 min-h-[500px] rounded-b-md bg-white">
        <Slate
          editor={editor}
          value={value}
          onChange={newValue => {
            setValue(newValue);

            // Check if content has changed
            const isChanged = JSON.stringify(newValue) !== JSON.stringify(initialValue);
            if (isChanged !== hasUnsavedChanges) {
              setHasUnsavedChanges(isChanged);
            }
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

      {/* Status Bar */}
      <div className="slate-statusbar text-sm text-gray-500 mt-2 flex justify-between">
        <div>
          {hasUnsavedChanges ? (
            <span className="text-amber-600">Unsaved changes</span>
          ) : (
            <span>No unsaved changes</span>
          )}
        </div>
        <div>
          Last saved: <span id="last-saved-time">Never</span>
        </div>
      </div>
    </div>
  );
};

// Custom Element component for rendering block elements
const Element = ({ attributes, children, element }) => {
  const style = { textAlign: element.align };

  switch (element.type) {
    case 'block-quote':
      return (
        <blockquote style={style} className="border-l-4 border-gray-300 pl-4 italic text-gray-600" {...attributes}>
          {children}
        </blockquote>
      );
    case 'bulleted-list':
      return (
        <ul style={style} className="list-disc pl-10" {...attributes}>
          {children}
        </ul>
      );
    case 'heading-one':
      return (
        <h1 style={style} className="text-2xl font-bold my-4" {...attributes}>
          {children}
        </h1>
      );
    case 'heading-two':
      return (
        <h2 style={style} className="text-xl font-bold my-3" {...attributes}>
          {children}
        </h2>
      );
    case 'list-item':
      return (
        <li style={style} {...attributes}>
          {children}
        </li>
      );
    case 'numbered-list':
      return (
        <ol style={style} className="list-decimal pl-10" {...attributes}>
          {children}
        </ol>
      );
    default:
      return (
        <p style={style} className="my-2" {...attributes}>
          {children}
        </p>
      );
  }
};

// Custom Leaf component for rendering inline elements
const Leaf = ({ attributes, children, leaf }) => {
  if (leaf.bold) {
    children = <strong>{children}</strong>;
  }

  if (leaf.italic) {
    children = <em>{children}</em>;
  }

  if (leaf.underline) {
    children = <u>{children}</u>;
  }

  if (leaf.code) {
    children = <code className="bg-gray-100 rounded px-1 py-0.5 font-mono text-sm">{children}</code>;
  }

  return <span {...attributes}>{children}</span>;
};

// Button for toggling marks (bold, italic, etc.)
const MarkButton = ({ format, icon }) => {
  const editor = useSlate();
  return (
    <button
      className={`p-1 rounded hover:bg-gray-200 ${
        isMarkActive(editor, format) ? 'bg-gray-200 text-indigo-600' : 'text-gray-700'
      }`}
      onMouseDown={event => {
        event.preventDefault();
        toggleMark(editor, format);
      }}
    >
      <span className="material-icons">{icon}</span>
    </button>
  );
};

// Button for toggling blocks (headings, lists, etc.)
const BlockButton = ({ format, icon }) => {
  const editor = useSlate();
  return (
    <button
      className={`p-1 rounded hover:bg-gray-200 ${
        isBlockActive(editor, format) ? 'bg-gray-200 text-indigo-600' : 'text-gray-700'
      }`}
      onMouseDown={event => {
        event.preventDefault();
        toggleBlock(editor, format);
      }}
    >
      <span className="material-icons">{icon}</span>
    </button>
  );
};

// Check if a mark is currently active
const isMarkActive = (editor, format) => {
  const marks = Editor.marks(editor);
  return marks ? marks[format] === true : false;
};

// Toggle a mark on or off
const toggleMark = (editor, format) => {
  const isActive = isMarkActive(editor, format);

  if (isActive) {
    Editor.removeMark(editor, format);
  } else {
    Editor.addMark(editor, format, true);
  }
};

// Check if a block format is currently active
const isBlockActive = (editor, format) => {
  const [match] = Editor.nodes(editor, {
    match: n =>
      !Editor.isEditor(n) && SlateElement.isElement(n) && n.type === format,
  });

  return !!match;
};

// Toggle a block format
const toggleBlock = (editor, format) => {
  const isActive = isBlockActive(editor, format);
  const isList = LIST_TYPES.includes(format);

  Transforms.unwrapNodes(editor, {
    match: n =>
      !Editor.isEditor(n) &&
      SlateElement.isElement(n) &&
      LIST_TYPES.includes(n.type),
    split: true,
  });

  let newProperties = {
    type: isActive ? 'paragraph' : isList ? 'list-item' : format,
  };

  Transforms.setNodes(editor, newProperties);

  if (!isActive && isList) {
    const block = { type: format, children: [] };
    Transforms.wrapNodes(editor, block);
  }
};

// Show a notification toast
const showNotification = (message, type = 'info') => {
  const notification = document.createElement('div');
  notification.className = `fixed bottom-4 right-4 p-4 rounded-md shadow-lg ${
    type === 'success'
      ? 'bg-green-50 text-green-800 border border-green-200'
      : type === 'error'
      ? 'bg-red-50 text-red-800 border border-red-200'
      : 'bg-blue-50 text-blue-800 border border-blue-200'
  }`;

  notification.textContent = message;
  document.body.appendChild(notification);

  // Remove after 3 seconds
  setTimeout(() => {
    notification.classList.add('opacity-0', 'transition-opacity', 'duration-500');
    setTimeout(() => {
      document.body.removeChild(notification);
    }, 500);
  }, 3000);
};

// Initialize the editor when the DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
  const editorContainer = document.getElementById('slate-editor');
  if (editorContainer) {
    ReactDOM.render(<SlateEditor />, editorContainer);
  }
});
