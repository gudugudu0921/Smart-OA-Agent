import { ref } from 'vue'
import { defineStore } from 'pinia'
import * as chatApi from '../api/chat'

export const useChatStore = defineStore('chat', () => {
  const sessions = ref([])
  const currentThreadId = ref('')
  const messages = ref([])
  const loading = ref(false)
  const sending = ref(false)

  async function loadSessions() {
    loading.value = true
    try {
      const { data } = await chatApi.listSessions()
      sessions.value = data.sessions
      return sessions.value
    } finally {
      loading.value = false
    }
  }

  async function createSession() {
    const { data } = await chatApi.createSession()
    await loadSessions()
    currentThreadId.value = data.thread_id
    messages.value = []
    return data
  }

  async function loadMessages(threadId) {
    loading.value = true
    try {
      await chatApi.getSession(threadId)
      const { data } = await chatApi.getSessionMessages(threadId)
      currentThreadId.value = threadId
      messages.value = data.messages
      return data.messages
    } finally {
      loading.value = false
    }
  }

  async function selectSession(threadId) {
    return loadMessages(threadId)
  }

  async function deleteSessionById(threadId) {
    await chatApi.deleteSession(threadId)
    sessions.value = sessions.value.filter((item) => item.thread_id !== threadId)
    if (currentThreadId.value === threadId) {
      currentThreadId.value = ''
      messages.value = []
    }
  }

  async function sendMessage(content) {
    if (!content.trim() || sending.value || !currentThreadId.value) return
    const requestThreadId = currentThreadId.value
    const userMessage = { role: 'user', content: content.trim() }
    messages.value.push(userMessage)
    sending.value = true
    try {
      const { data } = await chatApi.sendChat(requestThreadId, userMessage.content)
      if (currentThreadId.value === requestThreadId) {
        messages.value.push({ role: 'assistant', content: data.response, data: data.data, success: data.success })
      }
      await loadSessions()
      return data
    } catch (error) {
      if (currentThreadId.value === requestThreadId) {
        messages.value.push({ role: 'assistant', content: '消息发送失败，请稍后重试。', error: true })
      }
      throw error
    } finally {
      sending.value = false
    }
  }

  function reset() {
    sessions.value = []
    currentThreadId.value = ''
    messages.value = []
  }

  return { sessions, currentThreadId, messages, loading, sending, loadSessions, createSession, selectSession, deleteSession: deleteSessionById, loadMessages, sendMessage, reset }
})
