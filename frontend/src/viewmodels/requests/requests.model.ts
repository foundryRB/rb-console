import type { RequestsState, RequestOperation } from './requests.state';

export const selectUncertainOperations = (state: RequestsState): RequestOperation[] =>
    Object.values(state.operations).filter((operation) => operation.status === 'unknown');
