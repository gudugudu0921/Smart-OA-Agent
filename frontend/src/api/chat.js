import request from './request'

export const createSession = () => request.post('/chat/sessions')
export const listSessions = () => request.get('/chat/sessions')
export const getSession = (threadId) => request.get(`/chat/sessions/${threadId}`)
export const deleteSession = (threadId) => request.delete(`/chat/sessions/${threadId}`)
export const getSessionMessages = (threadId) => request.get(`/chat/sessions/${threadId}/messages`)
export const sendChat = (threadId, message) => request.post('/chat', { thread_id: threadId, message })
