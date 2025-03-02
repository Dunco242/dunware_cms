import React, { useCallback, useEffect, useMemo, useState, useRef } from 'react';
import ReactDOM from 'react-dom';
import { createEditor, Editor, Transforms, Text, Element as SlateElement, Range, Point } from 'slate';
import { Slate, Editable, withReact, useSlate, ReactEditor } from 'slate-react';
import { withHistory } from 'slate-history';
import isHotkey from 'is-hotkey';
import debounce from 'lodash/debounce';

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

        // Normalize content structure
        const content = parsedContent.children || parsedContent;

        // Ensure content is an array with at least one paragraph
        if (!Array.isArray(content) || content.length === 0) {
          return [
            {
              type: 'paragraph',
              children: [{ text: '' }],
            },
          ];
        }

        return content;
      } catch (error) {
        console.error('Error parsing document content:', error);
        return [
          {
            type: 'paragraph',
            children: [{ text: '' }],
          },
        ];
      }
    }

    return [
      {
        type: 'paragraph',
        children: [{ text: '' }],
      },
    ];
  }, []);

  // Create editor instance
  const [editor] = useState(() => withHistory(withReact(createEditor())));
  const [value, setValue] = useState(initialValue);
  const [isSaving, setIsSaving] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [selection, setSelection] = useState(null);

  // WebSocket related state
  const socketRef = useRef(null);
  const [isConnected, setIsConnected] = useState(false);
  const [remoteOperationsQueue, setRemoteOperationsQueue] = useState([]);
  const isRemoteChangeRef = useRef(false);

  // Get page elements
  const documentId = document.getElementById('document-id').value;
  const canEdit = document.getElementById('can-edit').value === 'True';
  const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

  // Function to send cursor position
  const sendCursorPosition = useCallback(
    debounce((selection) => {
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN && selection) {
        socketRef.current.send(
          JSON.stringify({
            type: 'cursor_position',
            selection: selection,
          })
        );
      }
    }, 100),
    [socketRef]
  );

  // Function to send content changes
  const sendContentChange = useCallback(
    debounce((operations) => {
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN && operations.length > 0) {
        socketRef.current.send(
          JSON.stringify({
            type: 'content_change',
            operations: operations,
          })
        );
      }
    }, 250),
    [socketRef]
  );

  // Handle remote operations
  useEffect(() => {
    if (remoteOperationsQueue.length > 0) {
      const operations = [...remoteOperationsQueue];
      setRemoteOperationsQueue([]);

      isRemoteChangeRef.current = true;

      try {
        operations.forEach(op => {
          Editor.withoutNormalizing(editor, () => {
            try {
              // Apply the remote operation based on its type
              if (op.type === 'insert_node') {
                Transforms.insertNodes(editor, op.node, { at: op.path });
              } else if (op.type === 'remove_node') {
                Transforms.delete(editor, { at: op.path });
              } else if (op.type === 'set_node') {
                Transforms.setNodes(editor, op.properties, { at: op.path });
              } else if (op.type === 'insert_text') {
                Transforms.insertText(editor, op.text, { at: op.path });
              } else if (op.type === 'remove_text') {
                Transforms.delete(editor, { at: op.path, distance: op.text.length });
              } else if (op.type === 'split_node') {
                Transforms.splitNodes(editor, { at: op.path });
              } else if (op.type === 'merge_node') {
                Transforms.mergeNodes(editor, { at: op.path });
              } else {
                console.warn('Unsupported operation:', op);
              }
            } catch (error) {
              console.error('Error applying remote operation:', error, op);
            }
          });
        });
      } finally {
        isRemoteChangeRef.current = false;
      }
    }
  }, [editor, remoteOperationsQueue]);

  // Initialize WebSocket connection
  useEffect(() => {
    // Get the WebSocket from the parent document
    socketRef.current = window.socket || null;

    // If socket doesn't exist in parent, try to initialize it here
    if (!socketRef.current) {
      const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
      const wsUrl = `${protocol}://${window.location.host}/wss/documents/${documentId}/`;

      try {
        socketRef.current = new WebSocket(wsUrl);

        socketRef.current.onopen = () => {
          console.log('WebSocket connection established from slate-editor');
          setIsConnected(true);
        };

        socketRef.current.onclose = () => {
          console.log('WebSocket connection closed from slate-editor');
          setIsConnected(false);
        };

        socketRef.current.onerror = (error) => {
          console.error('WebSocket error from slate-editor:', error);
          setIsConnected(false);
        };

        // Export socket to parent window
        window.socket = socketRef.current;
      } catch (error) {
        console.error('Error creating WebSocket connection:', error);
      }
    } else {
      setIsConnected(socketRef.current.readyState === WebSocket.OPEN);
    }

    // Handle WebSocket messages
    const handleMessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'content_change' && data.operations && Array.isArray(data.operations)) {
          // Queue remote operations for processing
          setRemoteOperationsQueue(prev => [...prev, ...data.operations]);
        } else if (data.type === 'save_confirmed') {
          handleSaveConfirmed(data);
        }
      } catch (error) {
        console.error('Error processing WebSocket message:', error);
      }
    };

    // Add message handler
    if (socketRef.current) {
      socketRef.current.addEventListener('message', handleMessage);
    }

    // Cleanup
    return () => {
      if (socketRef.current) {
        socketRef.current.removeEventListener('message', handleMessage);
      }
    };
  }, [documentId]);

  // Handle save confirmation
  const handleSaveConfirmed = (data) => {
    if (data.success) {
      setHasUnsavedChanges(false);
      setIsSaving(false);

      const successMsg = data.create_version
        ? `Created new version ${data.version}`
        : 'Document saved successfully';

      showNotification(successMsg, 'success');

      if (data.updated_at) {
        const lastSavedTimeElement = document.getElementById('last-saved-time');
        if (lastSavedTimeElement) {
          lastSavedTimeElement.innerText = new Date(data.updated_at).toLocaleString();
        }
      }
    } else {
      console.error('Error saving document:', data.error);
      showNotification('Error saving document: ' + data.error, 'error');
      setIsSaving(false);
    }
  };

  const renderElement = useCallback(props => <Element {...props} />, []);
  const renderLeaf = useCallback(props => <Leaf {...props} />, []);

  const saveDocument = async (createVersion = false) => {
    if (!hasUnsavedChanges && !createVersion) return;

    setIsSaving(true);

    try {
      // Try to save using WebSocket first
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        socketRef.current.send(
          JSON.stringify({
            type: 'save_document',
            content: { children: value },
            create_version: createVersion,
          })
        );

        // Wait for save_confirmed message in the WebSocket handler
        return;
      }

      // Fallback to HTTP if WebSocket is not available
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

        const successMsg = createVersion
          ? `Created new version ${data.version}`
          : 'Document saved successfully';

        showNotification(successMsg, 'success');

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

  // Auto-save when changes are made
  useEffect(() => {
    if (!canEdit) return;

    const interval = setInterval(() => {
      if (hasUnsavedChanges) {
        saveDocument();
      }
    }, 30000);

    return () => clearInterval(interval);
  }, [hasUnsavedChanges]);

  // Warn before leaving with unsaved changes
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

  // Track selection changes
  const handleSelectionChange = useCallback(() => {
    const sel = editor.selection;
    setSelection(sel);

    // Send selection to other users if it exists and is not collapsed
    if (sel && !Range.isCollapsed(sel) && canEdit) {
      sendCursorPosition(sel);
    }
  }, [editor, canEdit, sendCursorPosition]);

  const handleKeyDown = event => {
    if ((event.ctrlKey || event.metaKey) && event.key === 's') {
      event.preventDefault();
      saveDocument();
      return;
    }

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

      <div className="slate-editor border p-4 min-h-[500px] rounded-b-md bg-white">
        <Slate
          editor={editor}
          value={value}
          onChange={(newValue) => {
            // Only track changes if they're not from a remote user
            if (!isRemoteChangeRef.current) {
              // Get the operations since last change
              const ops = editor.operations
                .filter(op => {
                  // Filter out selection operations as they don't modify content
                  return op.type !== 'set_selection';
                })
                .map(op => {
                  // Clone the operation for safe transmission
                  return JSON.parse(JSON.stringify(op));
                });

              // Send operations to collaborators if there are any content changes
              if (ops.length > 0 && canEdit && isConnected) {
                sendContentChange(ops);
              }
            }

            // Always update the value
            setValue(newValue);

            // Track unsaved changes
            const isChanged = JSON.stringify(newValue) !== JSON.stringify(initialValue);
            if (isChanged !== hasUnsavedChanges) {
              setHasUnsavedChanges(isChanged);
            }
          }}
          onSelectionChange={handleSelectionChange}
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

const isMarkActive = (editor, format) => {
  const marks = Editor.marks(editor);
  return marks ? marks[format] === true : false;
};

const toggleMark = (editor, format) => {
  const isActive = isMarkActive(editor, format);

  if (isActive) {
    Editor.removeMark(editor, format);
  } else {
    Editor.addMark(editor, format, true);
  }
};

const isBlockActive = (editor, format) => {
  const [match] = Editor.nodes(editor, {
    match: n =>
      !Editor.isEditor(n) && SlateElement.isElement(n) && n.type === format,
  });

  return !!match;
};

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

  setTimeout(() => {
    notification.classList.add('opacity-0', 'transition-opacity', 'duration-500');
    setTimeout(() => {
      document.body.removeChild(notification);
    }, 500);
  }, 3000);
};

document.addEventListener('DOMContentLoaded', () => {
  const editorContainer = document.getElementById('slate-editor');
  if (editorContainer) {
    try {
      ReactDOM.render(<SlateEditor />, editorContainer);
    } catch (error) {
      console.error('Error rendering Slate editor:', error);
      editorContainer.innerHTML = `
        <div class="alert alert-danger">
          Unable to load document editor. Please refresh the page or contact support.
        </div>
      `;
    }
  }
});
