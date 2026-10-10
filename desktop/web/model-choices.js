export const qualified = model => model?.route ? model.route + '/' + model.id : model?.id ?? '';
// 任何已配置的模型都能设计、都能审核。默认：DeepSeek 设计、Agnes 审核；缺哪个就用已有的。
const pick = (models, preference) => preference ? models.find(m => qualified(m) === preference) ??
  (preference.includes('/') ? null : models.find(m => m.id === preference)) : null;
export function modelChoices(models, preference = '', reviewPreference = '') {
  const deepseek = models.find(m => /deepseek-v4-pro/i.test(m.id)) ?? models.find(m => /deepseek/i.test(m.id + ' ' + m.label));
  const agnes = models.find(m => /agnes-3\.0-flash/i.test(m.id)) ?? models.find(m => /agnes/i.test(m.id + ' ' + m.label));
  const design = pick(models, preference) ?? deepseek ?? agnes ?? models[0];
  return {design, review:pick(models, reviewPreference) ?? agnes ?? design};
}
