/** Retries retain the first answer; unanswered branch questions stay uncounted. */
export function recordFirstAnswer(answers:Record<string,boolean>,nodeId:string,correct:boolean):Record<string,boolean>{
 return Object.prototype.hasOwnProperty.call(answers,nodeId)?answers:{...answers,[nodeId]:correct};
}
